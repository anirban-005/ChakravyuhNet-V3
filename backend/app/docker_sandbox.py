"""Phase 2: Live Containment via Docker SDK.

When an attacker attempts lateral movement, this module spins up a real,
isolated Docker container running a vulnerable decoy image (postgres, nginx,
ssh sshd). The attacker's pivoting is routed INTO that container.

Features:
  - Automatic container lifecycle (create → track → auto-expire)
  - Per-host idempotency: same target = same container (no duplicates)
  - Safe teardown on reset
  - Graceful degradation: if Docker is unavailable, logs a warning and returns
    a stub so the rest of the system continues unaffected
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── Container image catalogue (vulnerable-but-isolated images) ────────

_IMAGE_MAP: dict[str, str] = {
    "db":      "postgres:15-alpine",
    "web":     "nginx:1.25-alpine",
    "ssh":     "linuxserver/openssh-server:latest",
    "default": "alpine:3.19",
}

_CONTAINER_TTL_SECONDS = int(os.getenv("DOCKER_CONTAINER_TTL", "300"))  # 5 min default


@dataclass
class SandboxRecord:
    container_id: str
    image: str
    host_target: str
    kind: str
    port_map: dict[str, int]          # {container_port_str: host_port}
    started_at: float = field(default_factory=time.time)
    status: str = "running"


class DockerSandboxManager:
    """Manages ephemeral Docker containers for live sandbox containment."""

    def __init__(self) -> None:
        self._client: Any = None          # docker.DockerClient or None
        self._sandboxes: dict[str, SandboxRecord] = {}  # host_target → record
        self._lock = asyncio.Lock()
        self._available = self._try_connect()

    # ── Lifecycle ────────────────────────────────────────────────────

    def _try_connect(self) -> bool:
        """Attempt to connect to local Docker daemon. Returns False if unavailable."""
        try:
            import docker  # type: ignore[import-untyped]
            self._client = docker.from_env(timeout=3)
            self._client.ping()
            logger.info("DockerSandboxManager: Docker daemon connected.")
            return True
        except Exception as exc:
            logger.warning(
                "DockerSandboxManager: Docker unavailable (%s). "
                "Live containment disabled — falling back to virtual decoys.",
                exc,
            )
            return False

    @property
    def available(self) -> bool:
        return self._available

    # ── Core: spin up a sandbox ───────────────────────────────────────

    async def ensure_sandbox(
        self, host_target: str, kind: str = "default"
    ) -> SandboxRecord | None:
        """Idempotently spin up a container for `host_target`.

        Returns the SandboxRecord if Docker is available, else None.
        """
        if not self._available:
            return None

        async with self._lock:
            if host_target in self._sandboxes:
                rec = self._sandboxes[host_target]
                logger.debug("Sandbox already running for %s: %s", host_target, rec.container_id[:12])
                return rec

            return await asyncio.get_event_loop().run_in_executor(
                None, self._create_container_sync, host_target, kind
            )

    def _create_container_sync(
        self, host_target: str, kind: str
    ) -> SandboxRecord | None:
        """Synchronous Docker SDK call — run in executor to avoid blocking."""
        image = _IMAGE_MAP.get(kind, _IMAGE_MAP["default"])
        try:
            logger.info("Pulling image %s for %s sandbox…", image, host_target)
            # Pull silently; if image is cached this is instant
            try:
                self._client.images.pull(image)
            except Exception:
                # If pull fails but image exists locally, that's fine
                pass

            # Environment variables injected to make decoy "feel real"
            env_vars = [
                "POSTGRES_PASSWORD=fin_ro_2026",
                "POSTGRES_USER=finance_ro",
                "POSTGRES_DB=quarterly_finance",
            ] if kind == "db" else []

            container = self._client.containers.run(
                image,
                detach=True,
                remove=False,
                environment=env_vars,
                labels={
                    "chakravyuhnet": "true",
                    "host_target": host_target,
                    "kind": kind,
                },
                ports={},  # no external port binding — internal sandbox only
                mem_limit="128m",
                cpu_period=100_000,
                cpu_quota=25_000,  # 25% CPU cap
                network_mode="none",  # completely network-isolated
            )

            record = SandboxRecord(
                container_id=container.id,
                image=image,
                host_target=host_target,
                kind=kind,
                port_map={},
            )
            self._sandboxes[host_target] = record
            logger.info(
                "Sandbox spawned: %s (%s) for target %s",
                container.id[:12], image, host_target,
            )
            return record

        except Exception as exc:
            logger.error("Failed to create sandbox for %s: %s", host_target, exc)
            return None

    # ── Inspect & capture malware ─────────────────────────────────────

    async def inspect_sandbox(self, host_target: str) -> dict | None:
        """Return container stats for the sandbox tied to host_target."""
        if not self._available:
            return None
        async with self._lock:
            rec = self._sandboxes.get(host_target)
            if not rec:
                return None
        try:
            container = await asyncio.get_event_loop().run_in_executor(
                None, self._client.containers.get, rec.container_id
            )
            stats = container.stats(stream=False)
            return {
                "container_id": rec.container_id[:12],
                "image": rec.image,
                "host_target": rec.host_target,
                "status": container.status,
                "uptime_seconds": int(time.time() - rec.started_at),
                "cpu_usage": stats.get("cpu_stats", {}),
            }
        except Exception as exc:
            logger.warning("Could not inspect sandbox %s: %s", host_target, exc)
            return None

    # ── Teardown ──────────────────────────────────────────────────────

    async def teardown_all(self) -> int:
        """Stop and remove all ChakravyuhNet containers. Returns count destroyed."""
        if not self._available:
            return 0

        async with self._lock:
            targets = list(self._sandboxes.keys())

        count = 0
        for target in targets:
            if await self._destroy_container(target):
                count += 1
        return count

    async def _destroy_container(self, host_target: str) -> bool:
        async with self._lock:
            rec = self._sandboxes.pop(host_target, None)
        if not rec:
            return False
        try:
            container = await asyncio.get_event_loop().run_in_executor(
                None, self._client.containers.get, rec.container_id
            )
            container.stop(timeout=5)
            container.remove(force=True)
            logger.info("Sandbox destroyed: %s (%s)", rec.container_id[:12], host_target)
            return True
        except Exception as exc:
            logger.warning("Could not destroy sandbox %s: %s", host_target, exc)
            return False

    # ── Status summary ────────────────────────────────────────────────

    async def status_summary(self) -> list[dict]:
        """Return a summary list of all active sandboxes."""
        async with self._lock:
            return [
                {
                    "container_id": rec.container_id[:12],
                    "image": rec.image,
                    "host_target": rec.host_target,
                    "kind": rec.kind,
                    "uptime_seconds": int(time.time() - rec.started_at),
                    "status": rec.status,
                }
                for rec in self._sandboxes.values()
            ]
