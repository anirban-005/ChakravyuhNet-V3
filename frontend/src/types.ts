export type NodeKind = "gateway" | "web" | "ssh" | "db" | "file" | "vault" | "attacker" | "tarpit";
export type NodeStatus = "cold" | "active" | "decoy" | "trapped" | "captured" | "burned" | "pulse";

export type Intent = "camouflage" | "snooping" | "movement" | "aggressive" | "weapon";
export type MapAction = "none" | "pulse" | "spawn_decoy" | "tarpit" | "vault";

export interface GraphPosition {
  x: number;
  y: number;
}

export interface MazeNode {
  id: string;
  label: string;
  kind: NodeKind;
  status: NodeStatus;
  position: GraphPosition;
}

export interface MazeEdge {
  id: string;
  source: string;
  target: string;
  animated: boolean;
  label?: string | null;
}

export interface TerminalEntry {
  command: string;
  output: string;
  intent: Intent;
  timestamp: string;
}

export interface LogEntry {
  message: string;
  timestamp: string;
  level: "info" | "warn" | "alert";
}

export interface ToolLine {
  text: string;
  timestamp: string;
  status: "running" | "slowed" | "crashed" | "done";
}

export interface SystemAlert {
  module: string;
  message: string;
  details: Record<string, unknown>;
  timestamp: string;
}

export interface VaultEntry {
  id: string;
  original_filename: string;
  stored_filename: string;
  sha256: string;
  size_bytes: number;
  content_type?: string | null;
  captured_at: string;
}

export interface ReportMetadata {
  report_id: string;
  created_at: string;
  stix_path: string;
  pdf_path?: string | null;
  payload_sha256?: string | null;
  attacker_ip: string;
}

export interface IntentClassification {
  intent: Intent;
  label: string;
  map_action: MapAction;
}

export interface SimulationState {
  phase: string;
  attacker_ip: string;
  attacker_position: string;
  active_intent: Intent | null;
  tarpit_active: boolean;
  vault_triggered: boolean;
  nodes: MazeNode[];
  edges: MazeEdge[];
  terminal: TerminalEntry[];
  brain_log: LogEntry[];
  tool_output: ToolLine[];
  vault: VaultEntry[];
  latest_report?: ReportMetadata | null;
  last_event: string;
  system_alerts: SystemAlert[];
}

export interface EventEnvelope {
  type: string;
  message: string;
  data: Record<string, unknown>;
  state: SimulationState;
  timestamp: string;
}
