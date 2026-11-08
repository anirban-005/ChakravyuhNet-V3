from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


NodeKind = Literal["gateway", "web", "ssh", "db", "file", "vault", "attacker", "tarpit"]
NodeStatus = Literal["cold", "active", "decoy", "trapped", "captured", "burned", "pulse"]

Intent = Literal["camouflage", "snooping", "movement", "aggressive", "weapon"]
MapAction = Literal["none", "pulse", "spawn_decoy", "tarpit", "vault"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GraphPosition(BaseModel):
    x: float
    y: float


class MazeNode(BaseModel):
    id: str
    label: str
    kind: NodeKind
    status: NodeStatus = "cold"
    position: GraphPosition


class MazeEdge(BaseModel):
    id: str
    source: str
    target: str
    animated: bool = False
    label: str | None = None


class TerminalEntry(BaseModel):
    command: str
    output: str
    intent: Intent = "camouflage"
    timestamp: datetime = Field(default_factory=utc_now)


class LogEntry(BaseModel):
    message: str
    timestamp: datetime = Field(default_factory=utc_now)
    level: Literal["info", "warn", "alert"] = "info"


class ToolLine(BaseModel):
    text: str
    timestamp: datetime = Field(default_factory=utc_now)
    status: Literal["running", "slowed", "crashed", "done"] = "running"


class VaultEntry(BaseModel):
    id: str
    original_filename: str
    stored_filename: str
    sha256: str
    size_bytes: int
    content_type: str | None = None
    captured_at: datetime = Field(default_factory=utc_now)


class ReportMetadata(BaseModel):
    report_id: str
    created_at: datetime = Field(default_factory=utc_now)
    stix_path: str
    pdf_path: str | None = None
    payload_sha256: str | None = None
    attacker_ip: str = "203.0.113.77"


class IntentClassification(BaseModel):
    """Sent to the frontend alongside every command response."""
    intent: Intent
    label: str
    map_action: MapAction


class SimulationState(BaseModel):
    phase: str = "idle"
    attacker_ip: str = "203.0.113.77"
    attacker_position: str = "edge-gw"
    active_intent: Intent | None = None
    tarpit_active: bool = False
    vault_triggered: bool = False
    nodes: list[MazeNode]
    edges: list[MazeEdge]
    terminal: list[TerminalEntry] = Field(default_factory=list)
    brain_log: list[LogEntry] = Field(default_factory=list)
    tool_output: list[ToolLine] = Field(default_factory=list)
    vault: list[VaultEntry] = Field(default_factory=list)
    latest_report: ReportMetadata | None = None
    last_event: str = "ready"


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=500)


class CommandResponse(BaseModel):
    command: str
    output: str
    intent: IntentClassification
    state: SimulationState


class EventEnvelope(BaseModel):
    type: str
    message: str
    data: dict = Field(default_factory=dict)
    state: SimulationState
    timestamp: datetime = Field(default_factory=utc_now)
