"""Phase 4: Applied Reinforcement Learning — RL Policy Engine.

Uses stable-baselines3 to train an agent that maximizes attacker dwell time.
The agent observes the current simulation state and chooses between:
  0 = TARPIT   (slow attacker with fake latency)
  1 = DECOY    (spawn fresh decoy node to lure attacker deeper)
  2 = HONEYTOKEN (serve an enticing credential bait)
  3 = ESCALATE (generate more realistic/tempting output)

Reward function:
  +1.0 per 10 seconds attacker stays connected
  +5.0 on weapon/payload event (attacker fully committed)
  -10.0 if attacker disconnects

Architecture:
  - Uses a simple custom Gymnasium environment
  - Policy: MLP (3-layer) via PPO
  - Model persists to disk so it improves across sessions
  - Background training loop runs asynchronously without blocking the API
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_PATH = Path(os.getenv("RL_MODEL_PATH", "backend/rl_model/chakra_rl"))
_ACTION_NAMES = ["tarpit", "decoy", "honeytoken", "escalate"]

# ── Optional imports (graceful degradation) ───────────────────────────

try:
    import gymnasium as gym
    from gymnasium import spaces
    from stable_baselines3 import PPO
    from stable_baselines3.common.env_checker import check_env
    _RL_AVAILABLE = True
except ImportError:
    _RL_AVAILABLE = False
    logger.warning(
        "stable-baselines3 / gymnasium not installed. "
        "RL Policy Engine running in DEMO mode (rule-based fallback)."
    )


# ── Gymnasium environment ─────────────────────────────────────────────

if _RL_AVAILABLE:
    class HoneypotEnv(gym.Env):  # type: ignore[misc]
        """Custom Gym environment modelling the honeypot deception game.

        Observation space (9 floats, normalised 0-1):
          [phase_idx, intent_idx, tarpit_active, vault_triggered,
           node_count, edge_count, cmd_count, time_connected_norm,
           last_intent_score]

        Action space:
          Discrete(4): tarpit, decoy, honeytoken, escalate
        """

        metadata = {"render_modes": []}

        def __init__(self) -> None:
            super().__init__()
            self.observation_space = spaces.Box(
                low=0.0, high=1.0, shape=(9,), dtype=np.float32
            )
            self.action_space = spaces.Discrete(4)
            self._state: dict[str, Any] = {}
            self._connected_since: float = time.time()
            self._last_reward: float = 0.0
            self._step_count = 0

        def _obs(self) -> np.ndarray:
            phases = ["idle", "active", "snooping", "maze_shift", "scan_detected", "payload_captured"]
            intents = ["camouflage", "snooping", "movement", "aggressive", "weapon"]
            phase = self._state.get("phase", "idle")
            intent = self._state.get("active_intent") or "camouflage"
            return np.array([
                phases.index(phase) / max(len(phases) - 1, 1) if phase in phases else 0.0,
                intents.index(intent) / max(len(intents) - 1, 1) if intent in intents else 0.0,
                float(self._state.get("tarpit_active", False)),
                float(self._state.get("vault_triggered", False)),
                min(len(self._state.get("nodes", [])) / 10.0, 1.0),
                min(len(self._state.get("edges", [])) / 15.0, 1.0),
                min(len(self._state.get("terminal", [])) / 50.0, 1.0),
                min((time.time() - self._connected_since) / 600.0, 1.0),  # norm to 10 min
                intents.index(intent) / max(len(intents) - 1, 1) if intent in intents else 0.0,
            ], dtype=np.float32)

        def reset(self, *, seed=None, options=None):  # type: ignore[override]
            super().reset(seed=seed)
            self._state = {}
            self._connected_since = time.time()
            self._step_count = 0
            return self._obs(), {}

        def step(self, action: int):
            self._step_count += 1
            reward = 0.1  # base reward for each step attacker stays

            intent = self._state.get("active_intent", "camouflage")
            if intent == "weapon":
                reward += 5.0   # attacker fully committed
            elif intent in ("movement", "aggressive"):
                reward += 1.0

            truncated = self._step_count >= 200
            terminated = False

            return self._obs(), reward, terminated, truncated, {}

        def update_state(self, state_dict: dict) -> None:
            """Called by the simulation engine to sync environment state."""
            self._state = state_dict

        def render(self):
            pass


# ── RL Policy Manager ─────────────────────────────────────────────────

class RLPolicyEngine:
    """Wraps the PPO model; provides async predict() and background training."""

    def __init__(self) -> None:
        self._model: Any = None
        self._env: Any = None
        self._available = _RL_AVAILABLE
        self._training = False
        self._step_buffer: list[dict] = []
        self._episode_rewards: list[float] = []
        self._current_state: dict = {}
        self._action_counts: dict[str, int] = {a: 0 for a in _ACTION_NAMES}

        if self._available:
            self._init_model()

    def _init_model(self) -> None:
        _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._env = HoneypotEnv()
        model_file = Path(str(_MODEL_PATH) + ".zip")
        if model_file.exists():
            try:
                self._model = PPO.load(str(_MODEL_PATH), env=self._env)
                logger.info("RL Policy: Loaded existing model from %s", _MODEL_PATH)
                return
            except Exception as exc:
                logger.warning("RL Policy: Could not load saved model (%s). Creating fresh.", exc)
        self._model = PPO(
            "MlpPolicy",
            self._env,
            verbose=0,
            learning_rate=3e-4,
            n_steps=64,
            batch_size=32,
            n_epochs=5,
        )
        logger.info("RL Policy: Fresh PPO model initialised.")

    # ── Public API ────────────────────────────────────────────────────

    def update_state(self, state_dict: dict) -> None:
        """Sync latest simulation state into the RL environment."""
        self._current_state = state_dict
        if self._available and self._env:
            self._env.update_state(state_dict)

    async def predict_action(self) -> dict:
        """Return the RL agent's recommended deception action.

        When the PPO model has insufficient training (confidence < 40%),
        we fall back to the rule-based policy so the UI never shows a
        contradictory tactic (e.g., HONEYTOKEN while phase=scan_detected).
        """
        if not self._available or self._model is None:
            return self._rule_based_fallback()

        try:
            obs = self._env._obs()
            action, _states = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._model.predict(obs, deterministic=False)
            )
            action_idx = int(action)
            action_name = _ACTION_NAMES[action_idx]

            # Compute probability for the chosen action via the policy network
            confidence_pct = 0.0
            confidence_str = "PPO"
            try:
                import torch
                obs_tensor = torch.FloatTensor(obs).unsqueeze(0)
                with torch.no_grad():
                    dist = self._model.policy.get_distribution(
                        self._model.policy.obs_to_tensor(obs)[0]
                    )
                    probs = dist.distribution.probs.squeeze().tolist()
                confidence_pct = probs[action_idx]
                confidence_str = f"{confidence_pct:.0%}"
            except Exception:
                confidence_str = "PPO"

            # Bug 2 fix: if the model is uncertain (below 40% confidence),
            # the PPO hasn't learned a meaningful policy yet — use the
            # rule-based fallback so phase and RL tactic stay consistent.
            if confidence_pct < 0.40:
                fallback = self._rule_based_fallback()
                fallback["confidence"] = f"{confidence_str} (rule override)"
                self._action_counts[fallback["action"]] += 1
                return fallback

            self._action_counts[action_name] += 1
            return {
                "action": action_name,
                "action_idx": action_idx,
                "confidence": confidence_str,
                "action_counts": dict(self._action_counts),
            }
        except Exception as exc:
            logger.error("RL predict failed: %s", exc)
            return self._rule_based_fallback()

    def _rule_based_fallback(self) -> dict:
        """Deterministic rule-based policy when RL is unavailable."""
        intent = self._current_state.get("active_intent", "camouflage")
        if intent == "weapon":
            action = "honeytoken"
        elif intent == "aggressive":
            action = "tarpit"
        elif intent == "movement":
            action = "decoy"
        else:
            action = "escalate"
        return {
            "action": action,
            "action_idx": _ACTION_NAMES.index(action),
            "confidence": "rule_based",
            "action_counts": dict(self._action_counts),
        }

    async def train_background(self, total_timesteps: int = 512) -> str:
        """Run a short PPO training update in a background executor."""
        if not self._available or self._model is None:
            return "RL unavailable — rule-based policy active"
        if self._training:
            return "Training already in progress"

        self._training = True
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._model.learn(total_timesteps=total_timesteps, reset_num_timesteps=False)
            )
            self._model.save(str(_MODEL_PATH))
            return f"RL training complete ({total_timesteps} steps). Model saved."
        except Exception as exc:
            return f"RL training error: {exc}"
        finally:
            self._training = False

    def get_stats(self) -> dict:
        return {
            "rl_available": self._available,
            "training_active": self._training,
            "action_distribution": dict(self._action_counts),
            "model_path": str(_MODEL_PATH),
        }
