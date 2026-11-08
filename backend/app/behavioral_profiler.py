"""Attacker Behavioral Profiling via Graph-based analysis.

Implements lightweight attacker fingerprinting using:
  1. Command sequence graph — directed edges between consecutive commands
  2. Timing cadence analysis — inter-keystroke delay patterns
  3. TTP signature matching — maps observed behavior to known APT patterns
  4. Risk scoring — composite score updated in real time

In production, this would feed a full Graph Neural Network (GNN) trained
on labelled APT command sequences.  Here we implement the full data pipeline
and a heuristic classifier that can be upgraded to a real GNN (e.g., via
PyTorch Geometric) once you have training data.

APT profiles reference:
  - APT28  (Fancy Bear)    — fast, automated scans; precise pivoting
  - APT41  (Double Dragon) — mixed espionage/criminal; SQLi + lateral movement
  - Lazarus Group          — financial focus; custom tools; slow methodical
  - Script Kiddie          — random tool usage, no clear objective
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── APT behavioral signatures ─────────────────────────────────────────

_APT_PROFILES: list[dict[str, Any]] = [
    {
        "name": "APT28 (Fancy Bear)",
        "tags": ["state-sponsored", "russia", "espionage"],
        "indicators": {
            "tools": ["nmap", "masscan", "mimikatz", "empire", "psexec"],
            "sequences": [
                ["nmap", "ssh", "grep"],
                ["ping", "traceroute", "nmap"],
            ],
            "timing": "fast",        # < 2s avg between commands
            "pivoting": True,        # SSH pivoting present
        },
        "risk": 95,
    },
    {
        "name": "APT41 (Double Dragon)",
        "tags": ["state-sponsored", "china", "financial"],
        "indicators": {
            "tools": ["sqlmap", "hydra", "gobuster", "socat"],
            "sequences": [
                ["sqlmap", "ssh", "wget"],
                ["gobuster", "curl", "python"],
            ],
            "timing": "medium",
            "pivoting": True,
        },
        "risk": 92,
    },
    {
        "name": "Lazarus Group",
        "tags": ["state-sponsored", "north-korea", "financial"],
        "indicators": {
            "tools": ["sqlite3", "strings", "cat", "find"],
            "sequences": [
                ["cat", "find", "strings"],
                ["sqlite3", "scp", "wget"],
            ],
            "timing": "slow",        # > 8s avg — methodical
            "pivoting": False,
        },
        "risk": 88,
    },
    {
        "name": "Script Kiddie",
        "tags": ["opportunistic", "automated"],
        "indicators": {
            "tools": ["nikto", "dirb", "hydra", "sqlmap"],
            "sequences": [
                ["nikto", "dirb", "hydra"],
            ],
            "timing": "variable",
            "pivoting": False,
        },
        "risk": 40,
    },
]


@dataclass
class CommandNode:
    command: str
    timestamp: float
    intent: str
    delay_from_prev: float = 0.0     # seconds since last command


@dataclass
class BehaviorProfile:
    session_id: str = "attacker-session-01"
    command_graph: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )
    command_sequence: list[CommandNode] = field(default_factory=list)
    tool_usage: Counter = field(default_factory=Counter)
    timing_samples: list[float] = field(default_factory=list)
    apt_match: str | None = None
    apt_confidence: float = 0.0
    risk_score: float = 0.0
    ttp_tags: list[str] = field(default_factory=list)
    pivoting_detected: bool = False
    last_updated: float = field(default_factory=time.time)


class BehavioralProfiler:
    """Builds a live behavioral fingerprint of the attacker."""

    def __init__(self) -> None:
        self.profile = BehaviorProfile()

    # ── Ingest ────────────────────────────────────────────────────────

    def ingest(self, command: str, intent: str, timestamp: float | None = None) -> None:
        """Record a new command and update all behavioral models."""
        ts = timestamp or time.time()
        first_token = command.strip().split()[0].lower() if command.strip() else ""

        # Calculate inter-command delay
        delay = 0.0
        if self.profile.command_sequence:
            delay = ts - self.profile.command_sequence[-1].timestamp
            if 0 < delay < 300:  # ignore gaps > 5 min (idle time)
                self.profile.timing_samples.append(delay)
                self.profile.timing_samples = self.profile.timing_samples[-100:]

        node = CommandNode(
            command=command,
            timestamp=ts,
            intent=intent,
            delay_from_prev=delay,
        )
        self.profile.command_sequence.append(node)
        self.profile.command_sequence = self.profile.command_sequence[-200:]

        # Update command graph edges
        if len(self.profile.command_sequence) >= 2:
            prev_token = self.profile.command_sequence[-2].command.split()[0].lower()
            self.profile.command_graph[prev_token][first_token] += 1

        # Count tool usage
        self.profile.tool_usage[first_token] += 1

        # Detect pivoting
        if intent == "movement":
            self.profile.pivoting_detected = True

        # Update TTP tags
        if intent == "weapon" and "WEAPON" not in self.profile.ttp_tags:
            self.profile.ttp_tags.append("WEAPON_USE")
        if intent == "aggressive" and "ACTIVE_SCAN" not in self.profile.ttp_tags:
            self.profile.ttp_tags.append("ACTIVE_SCAN")
        if intent == "snooping" and "CREDENTIAL_ACCESS" not in self.profile.ttp_tags:
            self.profile.ttp_tags.append("CREDENTIAL_ACCESS")

        # Re-classify APT match
        self._classify_apt()
        self.profile.last_updated = ts

    # ── APT classification ────────────────────────────────────────────

    def _classify_apt(self) -> None:
        """Heuristic APT matching — upgradeable to GNN with training data."""
        if len(self.profile.command_sequence) < 3:
            self.profile.apt_match = "Unknown — insufficient data"
            self.profile.apt_confidence = 0.0
            self.profile.risk_score = 10.0
            return

        used_tools = set(self.profile.tool_usage.keys())
        avg_delay = (
            sum(self.profile.timing_samples) / len(self.profile.timing_samples)
            if self.profile.timing_samples else 10.0
        )
        timing_label = (
            "fast" if avg_delay < 2.0
            else "medium" if avg_delay < 8.0
            else "slow"
        )

        best_match = None
        best_score = 0.0

        for profile in _APT_PROFILES:
            score = 0.0
            ind = profile["indicators"]

            # Tool overlap score (0-50 pts)
            overlap = len(used_tools & set(ind["tools"]))
            score += (overlap / max(len(ind["tools"]), 1)) * 50

            # Timing match (0-20 pts)
            if ind["timing"] == timing_label or ind["timing"] == "variable":
                score += 20

            # Pivoting match (0-20 pts)
            if ind["pivoting"] == self.profile.pivoting_detected:
                score += 20

            # Sequence match (0-10 pts)
            seq_tools = [n.command.split()[0].lower() for n in self.profile.command_sequence[-10:]]
            for seq in ind["sequences"]:
                if all(t in seq_tools for t in seq):
                    score += 10
                    break

            if score > best_score:
                best_score = score
                best_match = profile

        if best_match and best_score > 15:
            confidence = min(best_score / 100.0, 1.0)
            self.profile.apt_match = best_match["name"]
            self.profile.apt_confidence = round(confidence, 2)
            self.profile.risk_score = best_match["risk"] * confidence
        else:
            self.profile.apt_match = "Unknown Threat Actor"
            self.profile.apt_confidence = 0.0
            self.profile.risk_score = max(
                len(self.profile.command_sequence) * 0.5, 5.0
            )

    # ── Reporting ─────────────────────────────────────────────────────

    def get_summary(self) -> dict:
        avg_delay = (
            sum(self.profile.timing_samples) / len(self.profile.timing_samples)
            if self.profile.timing_samples else 0.0
        )
        # Top edges in command graph
        top_edges = []
        for src, dests in self.profile.command_graph.items():
            for dst, count in dests.items():
                top_edges.append((src, dst, count))
        top_edges.sort(key=lambda x: x[2], reverse=True)

        return {
            "session_id": self.profile.session_id,
            "apt_match": self.profile.apt_match,
            "apt_confidence": self.profile.apt_confidence,
            "risk_score": round(self.profile.risk_score, 1),
            "ttp_tags": self.profile.ttp_tags,
            "pivoting_detected": self.profile.pivoting_detected,
            "command_count": len(self.profile.command_sequence),
            "unique_tools": len(self.profile.tool_usage),
            "top_tools": self.profile.tool_usage.most_common(5),
            "avg_delay_seconds": round(avg_delay, 2),
            "timing_cadence": (
                "fast" if avg_delay < 2.0
                else "medium" if avg_delay < 8.0
                else "slow"
            ),
            "top_command_edges": [
                {"from": s, "to": d, "count": c} for s, d, c in top_edges[:8]
            ],
        }

    def reset(self) -> None:
        self.profile = BehaviorProfile()
