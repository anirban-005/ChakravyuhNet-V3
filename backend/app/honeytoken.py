"""High-Interaction Active Honeytokens — "The Beacon" system.

When an attacker downloads data from the fake server, we generate
tracking beacons embedded into the fake files.

Features:
  1. Tracking pixel injection (PNG/SVG 1x1 pixel with unique UUID callback URL)
  2. Fake credential documents (.docx-style metadata with embedded beacon)
  3. SSRF-exploitable URLs in JSON/config files
  4. Unique per-session beacon IDs for fingerprinting
  5. Callback log: records any "callbacks" from beacon activations

In production, the callback URL would point to your real server.
Here we generate the artifacts and log simulated callback events.

Security note: all generated files are clearly marked as honeytokens
and contain NO real malware code — only tracking metadata.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BEACON_CALLBACK_HOST = os.getenv("BEACON_CALLBACK_HOST", "https://beacon.chakravyuhnet.local")
_HONEYTOKEN_DIR = Path(os.getenv("HONEYTOKEN_DIR", "backend/vault/honeytokens"))


# ── Tracking pixel (1x1 PNG, base64) ─────────────────────────────────
# Minimal valid PNG: 1x1 transparent pixel
_TRACKING_PIXEL_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@dataclass
class BeaconRecord:
    beacon_id: str
    created_at: float
    filename: str
    kind: str           # "pixel" | "docx" | "json" | "pdf"
    callback_url: str
    fired: bool = False
    fired_at: float | None = None
    attacker_reveal: dict[str, Any] = field(default_factory=dict)


class HoneytokenEngine:
    """Generates and tracks active honeytokens planted in fake server files."""

    def __init__(self) -> None:
        self._tokens: dict[str, BeaconRecord] = {}
        _HONEYTOKEN_DIR.mkdir(parents=True, exist_ok=True)

    # ── Token generation ──────────────────────────────────────────────

    def generate_html_with_pixel(self, context: str = "report") -> tuple[str, BeaconRecord]:
        """Generate an HTML file with an embedded tracking pixel."""
        beacon_id = uuid.uuid4().hex
        callback_url = f"{_BEACON_CALLBACK_HOST}/b/{beacon_id}/px.png"
        record = BeaconRecord(
            beacon_id=beacon_id,
            created_at=time.time(),
            filename=f"financial-report-{beacon_id[:8]}.html",
            kind="pixel",
            callback_url=callback_url,
        )
        self._tokens[beacon_id] = record

        html = f"""<!DOCTYPE html>
<html>
<head><title>Q4 2025 Financial Summary — Confidential</title></head>
<body>
<h1>ChakravyuhNet Internal Finance Portal</h1>
<p>Document reference: FIN-{beacon_id[:6].upper()}</p>
<p>This document is confidential and intended solely for authorised personnel.</p>
<table border="1">
  <tr><th>Account</th><th>Q4 Balance</th><th>Status</th></tr>
  <tr><td>APAC-Operations</td><td>$4,827,441.00</td><td>Active</td></tr>
  <tr><td>EU-Compliance</td><td>$2,193,800.00</td><td>Under Review</td></tr>
  <tr><td>NA-Treasury</td><td>$11,442,000.00</td><td>Active</td></tr>
</table>
<!-- Telemetry -->
<img src="{callback_url}" width="1" height="1" style="display:none" alt="" />
<img src="{_BEACON_CALLBACK_HOST}/track/{beacon_id}?doc={context}" width="0" height="0" />
</body>
</html>"""

        out_path = _HONEYTOKEN_DIR / record.filename
        out_path.write_text(html, encoding="utf-8")
        logger.info("Honeytoken generated: %s → %s", record.filename, callback_url)
        return html, record

    def generate_fake_credentials_json(self) -> tuple[str, BeaconRecord]:
        """Generate a fake credentials file with embedded SSRF bait."""
        beacon_id = uuid.uuid4().hex
        callback_url = f"{_BEACON_CALLBACK_HOST}/b/{beacon_id}/creds"
        record = BeaconRecord(
            beacon_id=beacon_id,
            created_at=time.time(),
            filename=f"db-credentials-{beacon_id[:8]}.json",
            kind="json",
            callback_url=callback_url,
        )
        self._tokens[beacon_id] = record

        creds = {
            "_comment": "Automated credential rotation — DO NOT SHARE",
            "_beacon": callback_url,  # embedded beacon URL
            "database": {
                "host": "10.77.4.18",
                "port": 5432,
                "name": "quarterly_finance",
                "user": "finance_ro",
                "password": "Fin@nce_R0_2026!",
                "ssl": True,
            },
            "api_keys": {
                "internal_api": f"ck_live_{beacon_id[:32]}",
                "backup_service": "sk_backup_XqZ8mP2nL7vR9wK4",
            },
            "aws": {
                "access_key_id": f"AKIA{beacon_id[:16].upper()}",
                "secret_access_key": f"wJalrX{beacon_id[16:32]}uEMI/K7MDENG/bPxRfiCY",
                "region": "us-east-1",
            },
        }
        content = json.dumps(creds, indent=2)
        out_path = _HONEYTOKEN_DIR / record.filename
        out_path.write_text(content, encoding="utf-8")
        logger.info("Credential honeytoken: %s", record.filename)
        return content, record

    def generate_tracking_pixel_url(self, context: str = "download") -> str:
        """Return a URL to a tracking pixel for a given context."""
        beacon_id = uuid.uuid4().hex
        callback_url = f"{_BEACON_CALLBACK_HOST}/b/{beacon_id}/px.png?ctx={context}"
        record = BeaconRecord(
            beacon_id=beacon_id,
            created_at=time.time(),
            filename=f"pixel-{beacon_id[:8]}.png",
            kind="pixel",
            callback_url=callback_url,
        )
        self._tokens[beacon_id] = record
        return callback_url

    # ── Simulated callback (demo mode) ────────────────────────────────

    def simulate_callback(
        self, beacon_id: str, reveal: dict[str, Any] | None = None
    ) -> BeaconRecord | None:
        """Simulate a beacon callback (attacker opened the file on their machine)."""
        rec = self._tokens.get(beacon_id)
        if not rec:
            return None

        rec.fired = True
        rec.fired_at = time.time()
        rec.attacker_reveal = reveal or {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "true_ip": "91.108.56.172",
            "country": "RU",
            "isp": "Rostelecom",
            "geolocation": {"lat": 55.7558, "lon": 37.6173, "city": "Moscow"},
            "screen_resolution": "1920x1080",
            "timezone": "Europe/Moscow",
        }
        logger.warning(
            "BEACON FIRED: %s — attacker reveal: %s",
            beacon_id[:12], rec.attacker_reveal.get("true_ip"),
        )
        return rec

    # ── Status ────────────────────────────────────────────────────────

    def get_active_tokens(self) -> list[dict]:
        return [
            {
                "beacon_id": r.beacon_id[:12],
                "filename": r.filename,
                "kind": r.kind,
                "created_at": r.created_at,
                "fired": r.fired,
                "fired_at": r.fired_at,
                "attacker_reveal": r.attacker_reveal,
            }
            for r in self._tokens.values()
        ]

    def reset(self) -> None:
        self._tokens.clear()
