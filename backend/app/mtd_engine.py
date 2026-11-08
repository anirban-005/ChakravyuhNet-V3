"""Active Moving Target Defense (MTD) — Network topology mutation engine.

Simulates an SDN controller that automatically rotates the internal
network configuration to invalidate attacker reconnaissance:
  - IP address rotation (rotate subnet / host octets)
  - Port configuration shuffle (reassign service ports)
  - Topology restructuring (promote/demote nodes, add fake hops)
  - Scheduled or event-triggered mutation cycles

The MTD engine works purely at the simulation level — it manipulates
the maze topology and emitted fake IP/port data without touching any
real network infrastructure.  In a production deployment, this module
would interface with your SDN controller API (OpenFlow, ONOS, Ryu, etc.)

Mutation schedule:  every MTD_CYCLE_SECONDS (default 60).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import string
import time
from dataclasses import dataclass, field
from typing import Callable, Coroutine, Any

logger = logging.getLogger(__name__)

_MTD_CYCLE_SECONDS = int(os.getenv("MTD_CYCLE_SECONDS", "60"))
_MTD_ENABLED = os.getenv("MTD_ENABLED", "true").lower() in ("true", "1", "yes")

# ── Fake IP pool ───────────────────────────────────────────────────────

_SUBNET_BASES = ["10.77.4.", "10.77.8.", "10.77.16.", "172.18.9."]

_PORT_POOLS: dict[str, list[int]] = {
    "ssh":      [22, 2222, 2200, 8022, 4422],
    "http":     [80, 8080, 8000, 8888, 9080],
    "https":    [443, 8443, 9443, 4433],
    "postgres": [5432, 5433, 15432, 54320],
    "ftp":      [21, 2121, 9021],
}


@dataclass
class MTDSnapshot:
    cycle_number: int
    timestamp: float
    ip_map: dict[str, str]           # host_id → current fake IP
    port_map: dict[str, int]         # service_key → current fake port
    topology_seed: int               # seed used for this cycle's topology
    mutation_log: list[str] = field(default_factory=list)


class MovingTargetDefense:
    """Continuously rotates fake network configuration to defeat reconnaissance."""

    def __init__(self) -> None:
        self._cycle = 0
        self._start_time = time.time()
        self._current: MTDSnapshot = self._generate_snapshot()
        self._history: list[MTDSnapshot] = []
        self._listeners: list[Callable[[MTDSnapshot], Coroutine[Any, Any, None]]] = []
        self._task: asyncio.Task | None = None
        self._enabled = _MTD_ENABLED

    # ── Snapshot generation ───────────────────────────────────────────

    def _generate_snapshot(self) -> MTDSnapshot:
        self._cycle += 1
        seed = random.randint(0, 2**31)
        rng = random.Random(seed)

        # Rotate IPs
        subnet = rng.choice(_SUBNET_BASES)
        ip_map = {
            "fin-api-01":    f"{subnet}{rng.randint(10, 50)}",
            "quarterly-db":  f"{subnet}{rng.randint(51, 100)}",
            "backup-nfs":    f"{subnet}{rng.randint(101, 150)}",
            "edge-gw":       f"10.0.0.{rng.randint(1, 10)}",
            "claims-portal": f"{subnet}{rng.randint(151, 200)}",
        }

        # Rotate ports
        port_map = {
            "ssh":      rng.choice(_PORT_POOLS["ssh"]),
            "http":     rng.choice(_PORT_POOLS["http"]),
            "postgres": rng.choice(_PORT_POOLS["postgres"]),
            "ftp":      rng.choice(_PORT_POOLS["ftp"]),
        }

        # Build mutation log
        log = [
            f"[MTD Cycle {self._cycle}] IP rotation: fin-api-01 → {ip_map['fin-api-01']}",
            f"[MTD Cycle {self._cycle}] IP rotation: quarterly-db → {ip_map['quarterly-db']}",
            f"[MTD Cycle {self._cycle}] Port shuffle: SSH → :{port_map['ssh']}",
            f"[MTD Cycle {self._cycle}] Port shuffle: PostgreSQL → :{port_map['postgres']}",
            f"[MTD Cycle {self._cycle}] Topology seed updated — {seed:08x}",
        ]

        return MTDSnapshot(
            cycle_number=self._cycle,
            timestamp=time.time(),
            ip_map=ip_map,
            port_map=port_map,
            topology_seed=seed,
            mutation_log=log,
        )

    # ── Scheduler ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the automatic MTD rotation loop."""
        if not self._enabled:
            logger.info("MTD: Disabled via MTD_ENABLED=false")
            return
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._rotation_loop())
        logger.info("MTD: Rotation loop started (cycle every %ds)", _MTD_CYCLE_SECONDS)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def _rotation_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(_MTD_CYCLE_SECONDS)
                await self.mutate_now()
        except asyncio.CancelledError:
            pass

    # ── Manual / event-triggered mutation ─────────────────────────────

    async def mutate_now(self) -> MTDSnapshot:
        """Immediately trigger a full MTD cycle and notify all listeners."""
        self._current = self._generate_snapshot()
        self._history.append(self._current)
        self._history = self._history[-20:]  # keep last 20 cycles

        logger.info(
            "MTD cycle %d complete — %d IPs rotated, %d ports shuffled",
            self._cycle,
            len(self._current.ip_map),
            len(self._current.port_map),
        )

        for listener in self._listeners:
            try:
                await listener(self._current)
            except Exception as exc:
                logger.error("MTD listener error: %s", exc)

        return self._current

    # ── Listener registration ─────────────────────────────────────────

    def on_mutation(
        self, callback: Callable[[MTDSnapshot], Coroutine[Any, Any, None]]
    ) -> None:
        """Register an async callback invoked on every MTD cycle."""
        self._listeners.append(callback)

    # ── Query API ─────────────────────────────────────────────────────

    def current(self) -> MTDSnapshot:
        return self._current

    def resolve_ip(self, host_name: str) -> str:
        """Return the current fake IP for a given host name."""
        return self._current.ip_map.get(host_name, "10.77.4.99")

    def resolve_port(self, service: str) -> int:
        """Return the current fake port for a given service."""
        return self._current.port_map.get(service, 22)

    def get_status(self) -> dict:
        return {
            "enabled": self._enabled,
            "cycle_number": self._cycle,
            "cycle_interval_seconds": _MTD_CYCLE_SECONDS,
            "current_ip_map": self._current.ip_map,
            "current_port_map": self._current.port_map,
            "last_mutation": self._current.timestamp,
            "history_count": len(self._history),
            "mutation_log": self._current.mutation_log,
        }
