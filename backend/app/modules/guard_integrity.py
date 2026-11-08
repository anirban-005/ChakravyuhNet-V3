import asyncio
import logging
import os
import psutil
import httpx

logger = logging.getLogger("AntigravityAgent.Integrity")

C2_URL = os.getenv("C2_SERVER_URL", "http://127.0.0.1:8001")

# ── Attacker-grade offensive tools — always suspicious ─────────────────────
# NOTE: cmd.exe and powershell.exe are intentionally excluded here.
# They are routine admin/developer tools and generate constant false positives
# when the operator opens their own terminal.  The simulation already tracks
# attacker shell commands through the /api/shell/command route, making these
# process-level alerts for generic shells redundant and misleading.
SUSPICIOUS: set[str] = {
    "nmap.exe",
    "netcat.exe",
    "nc.exe",
    "wireshark.exe",
    "mimikatz.exe",
    "curl.exe",
    "wget.exe",
    "ssh.exe",
    "scp.exe",
    "ftp.exe",
    "wmic.exe",
    "mshta.exe",
    "cscript.exe",
    "wscript.exe",
    "regsvr32.exe",
}

# ── Processes that belong to THIS backend — never alert on these ────────────
# Collects the PID of the current Python interpreter and its parent chain so
# we never self-flag the FastAPI / uvicorn process tree.
def _own_pids() -> set[int]:
    own: set[int] = set()
    try:
        proc = psutil.Process(os.getpid())
        own.add(proc.pid)
        for p in proc.parents():
            own.add(p.pid)
        for c in proc.children(recursive=True):
            own.add(c.pid)
    except Exception:
        pass
    return own


# Keep track of which PIDs we've already alerted on
_seen_pids: set[int] = set()


def _snapshot_pids() -> dict[int, str]:
    """Return {pid: lower-name} for all currently running processes."""
    result: dict[int, str] = {}
    try:
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pid  = proc.info["pid"]
                name = (proc.info["name"] or "").lower()
                if name:
                    result[pid] = name
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass
    return result


def _get_parent_name(pid: int) -> str:
    """Return the lowercase name of the parent process, or empty string."""
    try:
        proc   = psutil.Process(pid)
        parent = proc.parent()
        return (parent.name() or "").lower() if parent else ""
    except Exception:
        return ""


async def start_integrity_guard():
    logger.info("Integrity Guard started (event-driven mode).")

    async with httpx.AsyncClient() as client:
        # Seed baseline — mark every currently-running process as already known
        baseline = _snapshot_pids()
        _seen_pids.update(baseline.keys())
        logger.info(f"Baseline: {len(_seen_pids)} existing processes ignored.")

        while True:
            try:
                own     = _own_pids()
                current = _snapshot_pids()

                for pid, name in current.items():
                    if pid in _seen_pids:
                        continue          # already reported or pre-existing
                    if pid in own:
                        _seen_pids.add(pid)
                        continue          # ignore our own process tree

                    _seen_pids.add(pid)

                    if name in SUSPICIOUS:
                        parent_name = _get_parent_name(pid)
                        display     = name  # keep .exe suffix for clarity
                        msg         = (
                            f"Suspicious process detected: {display} (PID: {pid})"
                            + (f" — spawned by {parent_name}" if parent_name else "")
                        )
                        logger.warning(msg)

                        payload = {
                            "module":  "integrity",
                            "message": msg,
                            "details": {
                                "name":        display,
                                "pid":         pid,
                                "parent_name": parent_name,
                            },
                        }
                        try:
                            await client.post(
                                f"{C2_URL}/api/alerts", json=payload, timeout=5.0
                            )
                        except Exception as e:
                            logger.error(f"Failed to send alert to C2: {e}")

                # Prune dead PIDs so _seen_pids doesn't grow unboundedly
                dead = _seen_pids - set(current.keys())
                _seen_pids.difference_update(dead)

            except Exception as e:
                logger.error(f"Error in integrity loop: {e}")

            # 0.5 s poll — fast enough to catch curl (which exits in ~0.3 s)
            await asyncio.sleep(0.5)

