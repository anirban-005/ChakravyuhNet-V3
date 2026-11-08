import { FormEvent, memo, useCallback, useEffect, useRef, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  Edge,
  Handle,
  MarkerType,
  Node,
  Position,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow
} from "reactflow";
import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  Crosshair,
  Database,
  Download,
  FileJson,
  FileText,
  LockKeyhole,
  Network,
  Play,
  RefreshCw,
  RotateCcw,
  Server,
  ShieldCheck,
  Skull,
  Terminal,
  Upload,
  Wifi,
  Biohazard,
  Radar
} from "lucide-react";
import { BehavioralProfile, LiveSandboxes, MTDPanel, RLPolicyEngine, KpiStrip } from "./components/IntelligencePanels";
import { BuzzerIndicator } from "./components/BuzzerIndicator";
import { useBuzzerEngine } from "./hooks/useBuzzerEngine";
import type { EventEnvelope, Intent, MazeEdge, MazeNode, SimulationState } from "./types";

const API_BASE = "";
const WS_BASE = `ws://${window.location.host}`;

/* ── Intent colour palette ─────────────────────────────────────────── */

const INTENT_COLORS: Record<Intent, string> = {
  camouflage: "#10B981",
  snooping:   "#F59E0B",
  movement:   "#F97316",
  aggressive: "#F43F5E",
  weapon:     "#EF4444",
};

const INTENT_LABELS: Record<Intent, string> = {
  camouflage: "RECON",
  snooping:   "SNOOP",
  movement:   "MOVE",
  aggressive: "SCAN",
  weapon:     "WEAPON",
};

const INTENT_DESCRIPTIONS: Record<Intent, string> = {
  camouflage: "Serving synthetic output — topology unchanged",
  snooping:   "Honeytoken access detected — node triggered",
  movement:   "Lateral movement identified — decoy spawned",
  aggressive: "Port scan detected — tarpit response active",
  weapon:     "PAYLOAD CAPTURED — vault isolation complete",
};

/* ── Empty state ───────────────────────────────────────────────────── */

const emptyState: SimulationState = {
  phase: "loading",
  attacker_ip: "203.0.113.77",
  attacker_position: "edge-gw",
  active_intent: null,
  tarpit_active: false,
  vault_triggered: false,
  nodes: [],
  edges: [],
  terminal: [],
  brain_log: [],
  tool_output: [],
  vault: [],
  latest_report: null,
  last_event: "Connecting...",
  system_alerts: []
};

/* ── Topology node renderer ────────────────────────────────────────── */

const iconByKind: Record<string, typeof Activity> = {
  attacker: Skull,
  gateway:  ShieldCheck,
  web:      Server,
  ssh:      Terminal,
  db:       Database,
  file:     FileText,
  vault:    LockKeyhole,
  tarpit:   Wifi,
};

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour:   "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(new Date(value));
}

function StatusNode({ data }: { data: MazeNode }) {
  let Icon = iconByKind[data.kind] ?? Crosshair;
  let statusClass = `topology-node--${data.status}`;
  
  if (data.kind === 'vault') {
    Icon = ShieldCheck;
    statusClass = 'topology-node--vault-safe';
  } else if (data.status === 'decoy') {
    Icon = Radar;
  } else if (data.status === 'trapped' || data.status === 'captured') {
    Icon = Biohazard;
  }

  let zoneLabel = null;
  let zoneColor = "";

  const isSafe = data.kind === 'vault' || (data.status === 'cold' && data.kind !== 'gateway');
  const isDummy = data.status === 'decoy' || data.status === 'trapped' || data.kind === 'tarpit';

  if (isSafe) {
    zoneLabel = "SECURE PRODUCTION";
    zoneColor = "var(--color-success)";
  } else if (isDummy) {
    zoneLabel = "ACTIVE DECEPTION";
    zoneColor = "var(--color-warning)";
  }

  return (
    <div style={{ position: 'relative' }}>
      {/* Zone Label above the node */}
      {zoneLabel && (
        <div style={{
          position: 'absolute',
          top: -18,
          left: 0,
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          fontWeight: 700,
          color: zoneColor,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          whiteSpace: 'nowrap'
        }}>
          {zoneLabel}
        </div>
      )}

      <div className={`topology-node ${statusClass}`}>
        {/* Status badge hanging from top */}
        {data.kind === 'vault' && (
          <div className="topology-status-badge topology-status-badge--isolated">ISOLATED</div>
        )}
        {data.status === 'trapped' && (
          <div className="topology-status-badge topology-status-badge--trapped">TRAPPED</div>
        )}
        {data.status === 'captured' && (
          <div className="topology-status-badge topology-status-badge--captured">CAPTURED</div>
        )}
        {data.status === 'decoy' && (
          <div className="topology-status-badge topology-status-badge--decoy">DECOY</div>
        )}

        <Handle type="target" position={Position.Left} />
        <div style={{display:'flex', alignItems:'center', justifyContent:'space-between', gap:6}}>
          <div style={{display:'flex', alignItems:'center', gap:8}}>
            <Icon size={16} aria-hidden="true" />
            <div>
              <strong>{data.label}</strong>
              <span style={{display:'block', fontFamily:'var(--font-mono)', fontSize:10, color:'var(--text-muted)', marginTop:2}}>
                {/* Fallback IP display */}
                {"10.x.x.x"}
              </span>
              <span style={{display:'block', fontSize:9, color:'var(--text-disabled)', marginTop:1}}>
                {data.kind} · {data.status}
              </span>
            </div>
          </div>
        </div>
        <Handle type="source" position={Position.Right} />
      </div>
    </div>
  );
}

const nodeTypes = {
  statusNode: memo(StatusNode)
};

/* ── Topology Canvas — must live inside ReactFlowProvider ──────────── */

interface TopologyCanvasProps {
  mazeNodes: MazeNode[];
  mazeEdges: MazeEdge[];
}

function TopologyCanvas({ mazeNodes, mazeEdges }: TopologyCanvasProps) {
  const { fitView } = useReactFlow();
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<MazeNode>([]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState([]);

  // Sync maze nodes into ReactFlow — never remount the canvas
  useEffect(() => {
    const nextNodes: Node<MazeNode | any>[] = mazeNodes.map((node) => ({
      id:        node.id,
      type:      "statusNode",
      data:      node,
      position:  node.position,
      draggable: true,
      zIndex:    10,
    }));

    setRfNodes(nextNodes);
  }, [mazeNodes, setRfNodes]);

  // Sync maze edges into ReactFlow
  useEffect(() => {
    const nextEdges: Edge[] = mazeEdges.map((edge) => ({
      id:        edge.id,
      source:    edge.source,
      target:    edge.target,
      animated:  edge.animated,
      label:     edge.label ?? undefined,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: {
        stroke:
          edge.label === "tarpit"   ? "#F43F5E" :
          edge.label === "trapdoor" ? "#EF4444" :
          edge.animated             ? "#F59E0B" :
          "rgba(255,255,255,0.18)",
        strokeWidth: edge.animated ? 2.5 : 1.5,
        filter: edge.animated ? "drop-shadow(0 0 6px rgba(245,158,11,0.6))" : undefined,
      },
    }));

    // Inject Blocked Redirection Edge
    const hasActiveDecoy = mazeNodes.some(n => n.status === 'trapped' || n.status === 'decoy');
    if (hasActiveDecoy) {
      const gateway = mazeNodes.find(n => n.kind === 'gateway');
      const vault = mazeNodes.find(n => n.kind === 'vault');
      if (gateway && vault) {
        nextEdges.push({
          id: 'blocked-route',
          source: gateway.id,
          target: vault.id,
          animated: false,
          label: '❌ BLOCKED',
          markerEnd: { type: MarkerType.ArrowClosed },
          style: {
            stroke: '#EF4444',
            strokeWidth: 2,
            strokeDasharray: '5 5'
          },
          labelStyle: { fill: '#EF4444', fontWeight: 700, fontSize: 10, fontFamily: 'var(--font-mono)' },
          labelBgStyle: { fill: '#0B1220' }
        });
      }
    }

    setRfEdges(nextEdges);
  }, [mazeNodes, mazeEdges, setRfEdges]);

  // Re-fit the view whenever the node/edge count changes (new nodes added/removed)
  const nodeCount = mazeNodes.length;
  const edgeCount = mazeEdges.length;
  useEffect(() => {
    if (nodeCount === 0) return;
    // Short delay lets ReactFlow finish positioning nodes before fitting
    const timer = setTimeout(() => {
      fitView({ padding: 0.18, duration: 500, includeHiddenNodes: true });
    }, 120);
    return () => clearTimeout(timer);
  }, [nodeCount, edgeCount, fitView]);

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.18, includeHiddenNodes: true }}
        minZoom={0.2}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
        onlyRenderVisibleElements={false}
        style={{ width: "100%", height: "100%" }}
      >
        <Background color="rgba(59,130,246,0.08)" gap={24} size={1.5} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

/* ── Main app ──────────────────────────────────────────────────────── */

function App() {
  const [state, setState] = useState<SimulationState>(emptyState);
  const [connection, setConnection] = useState<"live" | "offline" | "connecting">("connecting");
  const [command, setCommand] = useState("nmap -sS -Pn 10.77.4.0/24");
  const [busy, setBusy] = useState(false);
  const [lastIntent, setLastIntent] = useState<Intent | null>(null);

  // V2 Integration States
  const [behavioralProfile, setBehavioralProfile] = useState({ risk: 0, class: "Unknown", speed: "0 cmds/sec", commands: 0, confidence: 94 });
  const [rlPolicy, setRlPolicy] = useState({ action: "MONITOR", tarpit: 0, decoy: 0, honeytoken: 0, escalate: 0 });
  const [mtdCycles, setMtdCycles] = useState<{ id: number; ports: string; seed: string }[]>([]);
  const [sandboxes, setSandboxes] = useState({ dockerCount: 0, honeytokensFired: 0 });

  // Buzzer engine
  const buzzer = useBuzzerEngine();

  const fileInputRef   = useRef<HTMLInputElement | null>(null);
  const terminalEndRef = useRef<HTMLDivElement | null>(null);
  const brainEndRef    = useRef<HTMLDivElement | null>(null);

  /* ── WebSocket connection with auto-reconnect ─────────────────── */

  const wsRef      = useRef<WebSocket | null>(null);
  const retryRef   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryDelay = useRef(1000); // ms, doubles on each failure up to 30 s
  const destroyed  = useRef(false);

  const handleMessage = useCallback((message: MessageEvent) => {
    const event = JSON.parse(message.data) as EventEnvelope;
    setState(prev => ({
      ...event.state,
      system_alerts: prev.system_alerts || []
    }));

    if (event.data) {
      if (event.data.rl_action) {
        setRlPolicy({
          action:     event.data.rl_action as string,
          tarpit:     Number(event.data.rl_prob_tarpit    ?? 0.25),
          decoy:      Number(event.data.rl_prob_decoy     ?? 0.25),
          honeytoken: Number(event.data.rl_prob_honeytoken ?? 0.25),
          escalate:   Number(event.data.rl_prob_escalate  ?? 0.25),
        });
      }
      if (event.data.risk_score !== undefined || event.data.apt_match !== undefined) {
        setBehavioralProfile({
          risk:     Math.round(Number(event.data.risk_score) || 0),
          class:    (event.data.apt_match as string)       || "Unknown",
          speed:    (event.data.timing_cadence as string)  || "variable",
          commands: Number(event.data.command_count)       || 0,
          confidence: event.data.apt_confidence !== undefined ? Math.round(Number(event.data.apt_confidence) * 100) : 94
        });
      }
      if (event.data.mtdCycles) {
        setMtdCycles(event.data.mtdCycles as { id: number; ports: string; seed: string }[]);
      }
      if (event.data.dockerCount !== undefined || event.data.honeytokensFired !== undefined) {
        setSandboxes(prev => ({
          dockerCount:      (event.data.dockerCount      as number) ?? prev.dockerCount,
          honeytokensFired: (event.data.honeytokensFired as number) ?? prev.honeytokensFired
        }));
      }
    }

    if (event.type.startsWith("intent.")) {
      const intent = event.type.replace("intent.", "") as Intent;
      setLastIntent(intent);
      buzzer.triggerAlert(intent, Math.round(Number(event.data?.risk_score) || 50));
    }

    if (event.type === "system_alert") {
      const module = event.data.module as string;
      setState((prev) => ({
        ...prev,
        system_alerts: [...prev.system_alerts, {
          module,
          message:   event.data.message as string,
          details:   event.data.details as Record<string, unknown>,
          timestamp: new Date().toISOString()
        }].slice(-50)
      }));
      if (event.state && event.state.phase !== "idle") {
        buzzer.triggerSystemAlert(module);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connectWs = useCallback(() => {
    if (destroyed.current) return;

    setConnection("connecting");

    // Pull latest HTTP state whenever we (re)connect
    fetch(`${API_BASE}/api/state`)
      .then((r) => r.json())
      .then((data) => setState(prev => ({ ...data, system_alerts: prev.system_alerts || [] })))
      .catch(() => {/* backend still down — WS close will schedule retry */});

    const ws = new WebSocket(`${WS_BASE}/ws/events`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnection("live");
      retryDelay.current = 1000; // reset backoff on successful connect
    };

    ws.onclose = () => {
      if (destroyed.current) return;
      setConnection("offline");
      // Exponential backoff: 1 s → 2 → 4 → 8 → 16 → 30 s max
      const delay = retryDelay.current;
      retryDelay.current = Math.min(delay * 2, 30_000);
      retryRef.current = setTimeout(connectWs, delay);
    };

    ws.onerror = () => {
      // onerror always fires before onclose — let onclose handle retry
      setConnection("offline");
    };

    ws.onmessage = handleMessage;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handleMessage]);

  useEffect(() => {
    destroyed.current = false;
    connectWs();
    return () => {
      destroyed.current = true;
      if (retryRef.current) clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── Auto-scroll ──────────────────────────────────────────────── */

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ block: "end" });
    brainEndRef.current?.scrollIntoView({ block: "end" });
  }, [state.terminal.length, state.brain_log.length]);

  /* ── Vault alarm ──────────────────────────────────────────────── */

  useEffect(() => {
    if (state.vault_triggered) buzzer.triggerVaultAlarm();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.vault_triggered]);

  /* ── Clear intent flash after 2.5 s ──────────────────────────── */

  useEffect(() => {
    if (!lastIntent) return;
    const timer = setTimeout(() => setLastIntent(null), 2500);
    return () => clearTimeout(timer);
  }, [lastIntent]);

  /* ── Reset alarms on idle ──────────────────────────────────────── */

  useEffect(() => {
    if (state.phase === "idle") {
      buzzer.stopAll();
      setLastIntent(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase]);

  /* ── Actions ──────────────────────────────────────────────────── */

  const postStateAction = useCallback(async (path: string) => {
    buzzer.arm(); // arm audio on first user gesture
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}${path}`, { method: "POST" });
      const next     = await response.json();
      setState(prev => ({ ...(next.state ?? next), system_alerts: prev.system_alerts || [] }));
    } finally {
      setBusy(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submitCommand = async (event: FormEvent) => {
    event.preventDefault();
    if (!command.trim()) return;
    buzzer.arm(); // arm audio on first command (user gesture)
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/api/shell/command`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ command })
      });
      const payload = await response.json();
      setState(prev => ({ ...payload.state, system_alerts: prev.system_alerts || [] }));
      if (payload.intent) {
        const intent = payload.intent.intent as Intent;
        setLastIntent(intent);
        buzzer.triggerAlert(intent, behavioralProfile.risk);
      }
      setCommand("");
    } finally {
      setBusy(false);
    }
  };

  const uploadFile = async (file: File) => {
    buzzer.arm();
    setBusy(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${API_BASE}/api/payload/upload`, {
        method: "POST",
        body:   formData
      });
      const payload = await response.json();
      setState(prev => ({ ...payload.state, system_alerts: prev.system_alerts || [] }));
      setLastIntent("weapon");
      buzzer.triggerVaultAlarm();
    } finally {
      setBusy(false);
    }
  };

  const uploadSample = () => {
    const file = new File(
      ["demo payload: inert sample uploaded for ChakravyuhNet capture flow\n"],
      "dropper-demo.bin",
      { type: "application/octet-stream" }
    );
    void uploadFile(file);
  };

  const downloadReport = (kind: "stix" | "pdf") => {
    if (!state.latest_report) return;
    window.open(`${API_BASE}/api/reports/${state.latest_report.report_id}/${kind}`, "_blank");
  };

  const captured = state.vault[0];

  /* ── Connection label ─────────────────────────────────────────── */

  const connectionLabel: Record<typeof connection, string> = {
    live:       "LIVE",
    offline:    "OFFLINE",
    connecting: "CONNECTING",
  };

  /* ── Render ───────────────────────────────────────────────────── */

  return (
    <>
      <main className={`app-shell ${lastIntent ? `flash-${lastIntent}` : ""}`}>

        {/* ── Executive Command Bar ── */}
        <header className="topbar" role="banner">

          {/* Left — Brand */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div className="brand-lockup">
              <ShieldCheck size={24} aria-hidden="true" />
              <div>
                <h1>ChakravyuhNet</h1>
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "2px" }}>
                  <p>Active Defense Platform</p>
                  <span className="env-badge">ACTIVE DEFENSE</span>
                  <span className="classify-badge">INTERNAL USE ONLY</span>
                </div>
              </div>
            </div>
            {/* Topbar Metadata Row */}
            <div className="topbar-meta">
              <span className="topbar-meta-item">v3.2.1</span>
              <span className="topbar-meta-sep" />
              <span className="topbar-meta-item">Build 2026.06.11</span>
              <span className="topbar-meta-sep" />
              <span className="topbar-meta-item">ANIRBAN.B</span>
              <span className="topbar-meta-sep" />
              <span className="topbar-meta-item">Session DEF-2026-XXXX</span>
              <span className="topbar-meta-sep" />
              <span className="topbar-meta-item">Last sync: {new Date().toLocaleTimeString()}</span>
            </div>
          </div>

          {/* Center — Operation Status */}
          <div className="status-strip" aria-label="System status">
            <span className={`live-pill live-pill--${connection}`}>
              {connectionLabel[connection]}
            </span>

            <span className="status-item">
              <span className="status-label">Phase</span>
              <span className="status-value">{state.phase.replace(/_/g, " ")}</span>
            </span>

            <span className="status-item">
              <span className="status-label">Attacker</span>
              <span className="status-value">{state.attacker_ip}</span>
            </span>

            {state.tarpit_active && (
              <span className="tarpit-pill" role="status" aria-label="Tarpit active">
                TARPIT ACTIVE
              </span>
            )}
            {state.vault_triggered && (
              <span className="vault-pill" role="status" aria-label="Vault triggered">
                VAULT SEALED
              </span>
            )}
          </div>

          {/* Right — Actions */}
          <nav className="action-row" aria-label="Dashboard controls">
            {/* Buzzer widget — sits left of action buttons */}
            <BuzzerIndicator engine={buzzer} />

            <button
              type="button"
              id="btn-start"
              title="Start scenario"
              onClick={() => postStateAction("/api/scenario/start")}
              disabled={busy}
            >
              <Play size={15} aria-hidden="true" />
              <span>Start</span>
            </button>

            <button
              type="button"
              id="btn-reset"
              title="Reset scenario"
              onClick={() => {
                buzzer.stopAll();
                postStateAction("/api/scenario/reset");
              }}
              disabled={busy}
            >
              <RotateCcw size={15} aria-hidden="true" />
              <span>Reset</span>
            </button>

            <button
              type="button"
              id="btn-refresh"
              title="Refresh application"
              onClick={() => window.location.reload()}
              disabled={busy}
            >
              <RefreshCw size={15} aria-hidden="true" />
              <span>Refresh</span>
            </button>

            <button
              type="button"
              id="btn-sample"
              title="Upload sample payload"
              onClick={uploadSample}
              disabled={busy}
            >
              <Upload size={15} aria-hidden="true" />
              <span>Sample</span>
            </button>

            <button
              type="button"
              id="btn-vault"
              title="Choose payload file"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy}
            >
              <LockKeyhole size={15} aria-hidden="true" />
              <span>Vault</span>
            </button>

            <button
              type="button"
              id="btn-stix"
              title="Download STIX report"
              onClick={() => downloadReport("stix")}
              disabled={!state.latest_report}
              aria-label="Download STIX report"
            >
              <FileJson size={15} aria-hidden="true" />
            </button>

            <button
              type="button"
              id="btn-pdf"
              title="Download PDF report"
              onClick={() => downloadReport("pdf")}
              disabled={!state.latest_report}
              aria-label="Download PDF report"
            >
              <Download size={15} aria-hidden="true" />
            </button>

            <input
              ref={fileInputRef}
              type="file"
              className="hidden-input"
              aria-hidden="true"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void uploadFile(file);
                event.currentTarget.value = "";
              }}
            />
          </nav>
        </header>

        {/* ── New KPI Strip ── */}
        <KpiStrip
          threatScore={behavioralProfile.risk}
          activeSessions={behavioralProfile.commands}
          aiConfidence={behavioralProfile.confidence}
          decoyEngagements={sandboxes.honeytokensFired}
          policyDecision={rlPolicy.action}
          attackPhase={state.phase.replace(/_/g, " ")}
          lastEvent={state.last_event}
        />

        {/* ── Intent Alert Banner ── */}
        {lastIntent && (
          <div
            className="intent-banner"
            role="alert"
            aria-live="assertive"
            style={{
              borderColor: INTENT_COLORS[lastIntent],
              color: INTENT_COLORS[lastIntent],
            }}
          >
            <span
              className="intent-badge"
              style={{ background: INTENT_COLORS[lastIntent] }}
            >
              {INTENT_LABELS[lastIntent]}
            </span>
            <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>
              {INTENT_DESCRIPTIONS[lastIntent]}
            </span>
          </div>
        )}

        {/* ── Main Dashboard Grid ── */}
        <section className="battle-grid" aria-label="Security operations dashboard">

          {/* ══ LEFT COLUMN — Adversary Console ══ */}
          <div className="view-column">
            <div className="tab-bar">
              <div className="tab-item tab-item--active">
                ADVERSARY CONSOLE
              </div>
              <div className="tab-item">
                DECEPTION LAYER
                {connection === "live" && <span className="tab-live-pill">LIVE</span>}
              </div>
            </div>

            {/* Terminal Panel */}
            <section
              className="panel terminal-panel"
              aria-label="Adversary terminal feed"
              style={{ flexShrink: 0, minHeight: "260px", maxHeight: "340px" }}
            >
              <div className="panel-heading">
                <span>Analyst Terminal</span>
                <span>{state.last_event}</span>
              </div>

              <div className="terminal-col-headers" aria-hidden="true">
                <span>TIME</span>
                <span>INTENT</span>
                <span>COMMAND</span>
              </div>

              <div className="terminal-feed" role="log" aria-label="Terminal output">
                {state.terminal.map((entry) => (
                  <div
                    className={`terminal-entry terminal-entry--${entry.intent ?? "camouflage"}`}
                    key={`${entry.timestamp}-${entry.command}`}
                  >
                    <div className="prompt-line">
                      <span className="prompt-time">{formatTime(entry.timestamp)}</span>

                      <span className="prompt-intent">
                        <span
                          className="intent-dot"
                          style={{ background: INTENT_COLORS[entry.intent ?? "camouflage"] }}
                          aria-hidden="true"
                        />
                        <span
                          className="intent-chip"
                          style={{
                            background: `${INTENT_COLORS[entry.intent ?? "camouflage"]}18`,
                            color: INTENT_COLORS[entry.intent ?? "camouflage"],
                          }}
                        >
                          {INTENT_LABELS[entry.intent ?? "camouflage"]}
                        </span>
                      </span>

                      <span className="prompt-command">
                        <span className="prompt-symbol">$</span>
                        {entry.command}
                      </span>
                    </div>
                    {entry.output && <pre>{entry.output}</pre>}
                  </div>
                ))}
                <div ref={terminalEndRef} />
              </div>

              <form className="command-form" onSubmit={submitCommand} aria-label="Command input">
                <span className="command-prompt-symbol" aria-hidden="true">$</span>
                <input
                  id="command-input"
                  value={command}
                  onChange={(e) => setCommand(e.target.value)}
                  aria-label="Enter command"
                  spellCheck={false}
                  placeholder="Enter command..."
                  autoComplete="off"
                />
                <button
                  type="submit"
                  disabled={busy || !command.trim()}
                  title="Execute command"
                  aria-label="Execute command"
                >
                  <Terminal size={14} aria-hidden="true" />
                </button>
              </form>
            </section>

            {/* Tool Output Panel */}
            <section
              className="panel tool-panel"
              aria-label="Tool execution output"
              style={{ flex: 1, minHeight: 0 }}
            >
              <div className="panel-heading">
                <span>Tool Output</span>
                <Activity size={14} aria-hidden="true" style={{ color: "var(--text-disabled)" }} />
              </div>
              <div className="tool-feed" role="log" aria-label="Tool output log">
                {state.tool_output.map((line) => (
                  <div
                    className={`tool-line tool-line--${line.status}`}
                    key={`${line.timestamp}-${line.text}`}
                  >
                    <span>{formatTime(line.timestamp)}</span>
                    <span
                      className="severity-dot"
                      style={{
                        background:
                          line.status === "done"    ? "var(--color-success)" :
                          line.status === "slowed"  ? "var(--color-warning)" :
                          line.status === "crashed" ? "var(--color-critical)" :
                          "var(--color-info)"
                      }}
                      aria-hidden="true"
                    />
                    <p>{line.text}</p>
                  </div>
                ))}
              </div>
            </section>
          </div>

          {/* ══ RIGHT COLUMN — Defense Intelligence ══ */}
          <div className="view-column">
            <div className="section-title">
              <BrainCircuit size={14} aria-hidden="true" />
              <h2>Defense Intelligence</h2>
              <span className="section-badge">AI ENGINE</span>
            </div>

            {/* Live Topology Map */}
            <section
              className="panel map-panel"
              aria-label="Live network topology"
            >
              <div className="panel-heading">
                <span>Network Topology</span>
                <span className="panel-heading-meta">
                  {state.nodes.length} Nodes · {state.edges.length} Edges
                </span>
              </div>
              <div style={{ flex: 1, minHeight: 0, position: "relative" }}>
                <ReactFlowProvider>
                  <TopologyCanvas
                    mazeNodes={state.nodes}
                    mazeEdges={state.edges}
                  />
                </ReactFlowProvider>
              </div>
            </section>

            {/* AI Decision Log */}
            <section
              className="panel brain-panel"
              aria-label="AI decision log"
              style={{ flex: 1, minHeight: "140px", maxHeight: "200px" }}
            >
              <div className="panel-heading">
                <span>AI Decision Log</span>
                {captured ? (
                  <span title={`Captured payload: ${captured.sha256}`}>
                    {captured.sha256.slice(0, 16)}
                  </span>
                ) : (
                  <span style={{
                    display:'inline-flex', alignItems:'center', gap:4,
                    color:'var(--color-critical)', fontSize:9, fontWeight:700,
                    fontFamily:'var(--font-mono)', letterSpacing:'.04em'
                  }}>
                    ● VAULT ARMED
                  </span>
                )}
              </div>
              <div className="brain-feed" role="log" aria-label="AI brain log">
                {state.brain_log.map((entry) => (
                  <div
                    className={`brain-line brain-line--${entry.level}`}
                    key={`${entry.timestamp}-${entry.message}`}
                  >
                    <span>{formatTime(entry.timestamp)}</span>
                    <span
                      className={`severity-dot severity-dot--${entry.level}`}
                      aria-hidden="true"
                    />
                    <div>
                      <p>{entry.message}</p>
                      {entry.level === 'alert' && (
                        <div style={{marginTop:3, display:'flex', gap:4}}>
                          <span className="alert-badge alert-badge--critical">CRITICAL</span>
                          <span className="mitre-tag">TA0008</span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                <div ref={brainEndRef} />
              </div>
            </section>

            {/* Intelligence Panels Row */}
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              <BehavioralProfile profile={behavioralProfile} rlAction={rlPolicy.action} phase={state.phase.replace(/_/g, " ")} />
              <RLPolicyEngine policy={rlPolicy} />

              {/* Side-by-side Sandboxes and MTD Panel */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
                <LiveSandboxes stats={sandboxes} />
                <MTDPanel cycles={mtdCycles} />
              </div>

              {/* System Alerts / Guard Log */}
              <section
                className="panel"
                aria-label="System guard alerts"
                style={{ overflow: "hidden" }}
              >
                <div className="panel-heading">
                  <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <AlertTriangle size={13} aria-hidden="true" style={{ color: "var(--color-warning)", opacity: 0.8 }} />
                    Guard Alerts
                  </span>
                  <Activity size={13} aria-hidden="true" style={{ color: "var(--text-disabled)" }} />
                </div>
                <div
                  className="brain-feed"
                  role="log"
                  aria-label="Guard module alerts"
                  style={{ maxHeight: "150px", overflowY: "auto" }}
                >
                  {state.system_alerts.length === 0 ? (
                    <div className="brain-line">
                      <span>--:--:--</span>
                      <span
                        className="severity-dot"
                        style={{ background: "var(--color-success)" }}
                        aria-hidden="true"
                      />
                      <div>
                        <p style={{ color: "var(--text-muted)" }}>
                          No active alerts — all guard modules nominal
                        </p>
                      </div>
                    </div>
                  ) : (
                    state.system_alerts.map((alert, idx) => (
                      <div className="brain-line" key={idx}>
                        <span>{formatTime(alert.timestamp)}</span>
                        <span
                          className="severity-dot"
                          style={{ background: "var(--color-critical)" }}
                          aria-hidden="true"
                        />
                        <div>
                          <p style={{ color: "var(--text-secondary)" }}>
                            <span
                              className="alert-badge alert-badge--critical"
                              style={{ marginRight: "6px" }}
                            >
                              {alert.module.toUpperCase()}
                            </span>
                            {alert.message}
                          </p>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </section>
            </div>
          </div>
        </section>
      </main>
    </>
  );
}

export default App;
