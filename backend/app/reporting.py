from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .models import ReportMetadata, SimulationState, VaultEntry


def _stix_id(kind: str) -> str:
    return f"{kind}--{uuid.uuid4()}"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_stix_bundle(state: SimulationState, payload: VaultEntry) -> dict:
    created = _now()
    identity_id = _stix_id("identity")
    attacker_id = _stix_id("ipv4-addr")
    malware_id = _stix_id("malware")
    report_id = _stix_id("report")

    commands = [
        {
            "command": entry.command,
            "timestamp": entry.timestamp.isoformat(),
            "output_preview": entry.output[:280],
        }
        for entry in state.terminal[-20:]
    ]

    events = [
        {
            "message": entry.message,
            "level": entry.level,
            "timestamp": entry.timestamp.isoformat(),
        }
        for entry in state.brain_log[-30:]
    ]

    return {
        "type": "bundle",
        "id": _stix_id("bundle"),
        "objects": [
            {
                "type": "identity",
                "spec_version": "2.1",
                "id": identity_id,
                "created": created,
                "modified": created,
                "name": "ChakravyuhNet",
                "identity_class": "system",
            },
            {
                "type": "ipv4-addr",
                "spec_version": "2.1",
                "id": attacker_id,
                "value": state.attacker_ip,
            },
            {
                "type": "malware",
                "spec_version": "2.1",
                "id": malware_id,
                "created": created,
                "modified": created,
                "name": f"Captured payload {payload.sha256[:12]}",
                "is_family": False,
                "description": "Payload captured by ChakravyuhNet and stored inertly for analysis.",
                "x_chakravyuhnet_sha256": payload.sha256,
                "x_chakravyuhnet_filename": payload.original_filename,
                "x_chakravyuhnet_size_bytes": payload.size_bytes,
            },
            {
                "type": "attack-pattern",
                "spec_version": "2.1",
                "id": _stix_id("attack-pattern"),
                "created": created,
                "modified": created,
                "name": "Network Service Discovery",
                "external_references": [
                    {
                        "source_name": "mitre-attack",
                        "external_id": "T1046",
                    }
                ],
            },
            {
                "type": "report",
                "spec_version": "2.1",
                "id": report_id,
                "created": created,
                "modified": created,
                "name": "ChakravyuhNet honeypot incident report",
                "published": created,
                "report_types": ["threat-report"],
                "object_refs": [identity_id, attacker_id, malware_id],
                "x_chakravyuhnet_commands": commands,
                "x_chakravyuhnet_ai_events": events,
                "x_chakravyuhnet_phase": state.phase,
            },
        ],
    }


def write_report_files(
    reports_dir: Path, state: SimulationState, payload: VaultEntry
) -> ReportMetadata:
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_id = uuid.uuid4().hex[:12]
    stix_path = reports_dir / f"{report_id}.stix.json"
    pdf_path = reports_dir / f"{report_id}.pdf"

    bundle = build_stix_bundle(state, payload)
    stix_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    _write_pdf(pdf_path, state, payload, report_id)

    return ReportMetadata(
        report_id=report_id,
        stix_path=str(stix_path),
        pdf_path=str(pdf_path),
        payload_sha256=payload.sha256,
        attacker_ip=state.attacker_ip,
    )


def _write_pdf(
    pdf_path: Path, state: SimulationState, payload: VaultEntry, report_id: str
) -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)

    command_lines = "<br/>".join(
        f"{entry.timestamp.isoformat()} - {entry.command}"
        for entry in state.terminal[-12:]
    )
    brain_lines = "<br/>".join(
        f"{entry.timestamp.isoformat()} - {entry.message}"
        for entry in state.brain_log[-12:]
    )

    story = [
        Paragraph("ChakravyuhNet Incident Report", styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"Report ID: {report_id}", styles["Normal"]),
        Paragraph(f"Attacker IP: {state.attacker_ip}", styles["Normal"]),
        Paragraph(f"Captured file: {payload.original_filename}", styles["Normal"]),
        Paragraph(f"SHA-256: {payload.sha256}", styles["Normal"]),
        Paragraph(f"Size: {payload.size_bytes} bytes", styles["Normal"]),
        Spacer(1, 12),
        Paragraph("Observed Commands", styles["Heading2"]),
        Paragraph(command_lines or "No commands recorded.", styles["BodyText"]),
        Spacer(1, 12),
        Paragraph("AI Decisions", styles["Heading2"]),
        Paragraph(brain_lines or "No AI decisions recorded.", styles["BodyText"]),
    ]
    doc.build(story)
