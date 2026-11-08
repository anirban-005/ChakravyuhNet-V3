import {
  Activity,
  Container,
  Eye,
  Layers,
  Shield,
  ShieldAlert,
  Target,
  Zap,
} from "lucide-react";

/* ─────────────────────────────────────────────────────────────────────────
   INTELLIGENCE PANELS
   Enterprise SOC component set — no emoji, Lucide icons only,
   CSS-variable design tokens, zero Tailwind inline classes.
   ───────────────────────────────────────────────────────────────────────── */

/* ── KPI Strip ───────────────────────────────────────────────────────── */

interface KpiStripProps {
  threatScore: number;
  activeSessions: number;
  aiConfidence: number;
  decoyEngagements: number;
  policyDecision: string;
  attackPhase: string;
  lastEvent: string;
}

export function KpiStrip({
  threatScore,
  activeSessions,
  aiConfidence,
  decoyEngagements,
  policyDecision,
  attackPhase,
  lastEvent,
}: KpiStripProps) {
  const scoreColor =
    threatScore >= 75
      ? "var(--color-critical)"
      : threatScore >= 40
      ? "var(--color-warning)"
      : "var(--color-success)";

  return (
    <div className="kpi-strip">
      <div className="kpi-card">
        <span className="kpi-label">Threat Score</span>
        <span className="kpi-value" style={{ color: scoreColor }}>{threatScore}/100</span>
      </div>
      <div className="kpi-card">
        <span className="kpi-label">Active Sessions</span>
        <span className="kpi-value">{activeSessions}</span>
      </div>
      <div className="kpi-card">
        <span className="kpi-label">AI Confidence</span>
        <span className="kpi-value" style={{ color: "var(--color-success)" }}>{aiConfidence}%</span>
      </div>
      <div className="kpi-card">
        <span className="kpi-label">Decoy Engagements</span>
        <span className="kpi-value" style={{ color: decoyEngagements > 0 ? "var(--color-warning)" : "var(--text-primary)" }}>
          {decoyEngagements}
        </span>
      </div>
      <div className="kpi-card">
        <span className="kpi-label">Policy Decision</span>
        <span className="kpi-value" style={{ color: "var(--accent-primary)", textTransform: "uppercase" }}>
          {policyDecision}
        </span>
      </div>
      <div className="kpi-card">
        <span className="kpi-label">Attack Phase</span>
        <span className="kpi-value" style={{ color: "var(--color-warning)", textTransform: "uppercase" }}>
          {attackPhase}
        </span>
      </div>
      <div className="kpi-card">
        <span className="kpi-label">Last Event</span>
        <span className="kpi-value" style={{ fontSize: "14px" }}>{lastEvent}</span>
      </div>
    </div>
  );
}

/* ── Behavioral Profile Panel ───────────────────────────────────────── */

interface BehavioralProfileProps {
  profile: {
    risk:     number;
    class:    string;
    speed:    string;
    commands: number;
  };
  rlAction: string;
  phase: string;
}

export function BehavioralProfile({ profile, rlAction, phase }: BehavioralProfileProps) {
  const isHigh     = profile.risk >= 70;
  const isMedium   = profile.risk >= 40 && profile.risk < 70;

  const scoreColor = isHigh
    ? "var(--color-critical)"
    : isMedium
      ? "var(--color-warning)"
      : "var(--color-success)";

  const badgeStyle: React.CSSProperties = {
    background: `${scoreColor}18`,
    color:       scoreColor,
    borderColor: `${scoreColor}35`,
  };

  const threatLabel = isHigh ? "HIGH RISK" : isMedium ? "MODERATE" : "LOW RISK";
  const isEscalated = rlAction.toLowerCase() === "escalate" || profile.risk > 60;

  return (
    <section className="intel-card" aria-label="Behavioral risk profile">
      <div className="intel-card-header">
        <span className="intel-card-title" style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <ShieldAlert size={13} aria-hidden="true" style={{ color: "var(--text-muted)" }} />
          Behavioral Profile
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {isEscalated && (
            <span style={{ fontSize: "9px", fontWeight: 700, color: "var(--color-critical)", display: "flex", alignItems: "center", gap: "4px" }}>
              <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--color-critical)" }} />
              ESCALATED
            </span>
          )}
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "10px",
              fontWeight: 700,
              padding: "2px 7px",
              borderRadius: "4px",
              border: "1px solid",
              ...badgeStyle,
            }}
          >
            {threatLabel}
          </span>
        </div>
      </div>

      <div className="intel-card-body">
        {/* ROW 1: Score & Attribution */}
        <div className="bp-score-section">
          <div className="bp-score-left">
            <span style={{ fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", fontWeight: 600 }}>
              THREAT SCORE
            </span>
            <div className="bp-score-value" style={{ color: scoreColor }}>
              {profile.risk}
              <span className="bp-score-denom" style={{ fontSize: "20px", color: "var(--text-muted)" }}>/100</span>
            </div>
          </div>
          <div className="bp-score-right">
            <span style={{ fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", fontWeight: 600 }}>
              ATTRIBUTION
            </span>
            <span className="threat-class-badge" style={{ ...badgeStyle, fontSize: "10px", padding: "2px 6px" }}>
              {profile.class}
            </span>
            <span className="bp-attr-sub">Nation-state APT</span>
          </div>
        </div>

        {/* ROW 2: Confidence Bar */}
        <div className="bp-confidence-section">
          <div className="bp-confidence-header">
            <span className="bp-confidence-label">AI CONFIDENCE</span>
            <span className="bp-confidence-value" style={{ color: "var(--color-success)" }}>94%</span>
          </div>
          <div className="score-bar" style={{ width: "100%", height: "4px" }} aria-hidden="true">
            <div
              className="score-bar-fill"
              style={{
                width:      `${profile.risk}%`,
                background: scoreColor,
              }}
            />
          </div>
        </div>

        {/* ROW 3: Phase & Recommended */}
        <div className="bp-phase-grid">
          <div className="bp-phase-card">
            <div className="bp-phase-label">ATTACK PHASE</div>
            <div className="bp-phase-value" style={{ color: "var(--color-warning)" }}>{phase || "RECON"}</div>
          </div>
          <div className="bp-phase-card">
            <div className="bp-phase-label">RECOMMENDED</div>
            <div className="bp-phase-value" style={{ color: "var(--color-critical)" }}>{rlAction.toUpperCase()}</div>
          </div>
        </div>

        {/* ROW 4: Metadata Strip */}
        <div className="bp-meta-strip">
          <span className="bp-meta-item">CADENCE · {profile.speed}s</span>
          <span className="bp-meta-item">COMMANDS · {profile.commands}</span>
          <span className="bp-meta-item">TA0008</span>
        </div>
      </div>
    </section>
  );
}

/* ── RL Policy Engine Panel ──────────────────────────────────────────── */

interface RLPolicyProps {
  policy: {
    action:     string;
    tarpit:     number;
    decoy:      number;
    honeytoken: number;
    escalate:   number;
  };
}

const POLICY_CARDS: {
  key: keyof Omit<RLPolicyProps["policy"], "action">;
  label: string;
  icon: typeof Target;
}[] = [
  { key: "tarpit",     label: "Tarpit",     icon: Zap      },
  { key: "decoy",      label: "Decoy",      icon: Eye      },
  { key: "honeytoken", label: "Honeytoken", icon: Target   },
  { key: "escalate",   label: "Escalate",   icon: Shield   },
];

export function RLPolicyEngine({ policy }: RLPolicyProps) {
  return (
    <section className="intel-card" aria-label="Reinforcement learning policy engine">
      <div className="intel-card-header">
        <span className="intel-card-title" style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <Activity size={13} aria-hidden="true" style={{ color: "var(--text-muted)" }} />
          Policy Engine
        </span>
      </div>

      <div className="intel-card-body" style={{ paddingBottom: "12px" }}>
        {/* Active action header */}
        <div className="policy-action-header">
          <span style={{
            display:'inline-flex', alignItems:'center', gap:5,
            background:'rgba(59,130,246,.10)',
            border:'1px solid rgba(59,130,246,.3)',
            color:'#60A5FA',
            fontSize:9, fontWeight:700,
            padding:'2px 8px', borderRadius:4,
            fontFamily:'var(--font-mono)',
            letterSpacing:'.04em'
          }}>
            ● {policy.action.toUpperCase()} ACTIVE
          </span>
        </div>

        {/* 2×2 action probability cards */}
        <div className="policy-cards">
          {POLICY_CARDS.map(({ key, label, icon: Icon }) => {
            const value      = policy[key];
            const isActive   = policy.action.toLowerCase() === label.toLowerCase();
            const pct        = Math.round(value * 100);

            return (
              <div
                key={key}
                className={`policy-card${isActive ? " policy-card--active" : ""}`}
                aria-label={`${label}: ${pct}% probability${isActive ? " (active)" : ""}`}
              >
                <div className="policy-card-label">
                  <Icon size={10} aria-hidden="true" />
                  {label}
                </div>
                <div className="policy-card-value">
                  {pct}<span style={{ fontSize: "11px", fontWeight: 500, color: "var(--text-muted)" }}>%</span>
                </div>
                <div className="policy-card-bar" aria-hidden="true">
                  <div
                    className="policy-card-bar-fill"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ── Moving Target Defense Panel ─────────────────────────────────────── */

interface MTDPanelProps {
  cycles: { id: number; ports: string; seed: string }[];
}

export function MTDPanel({ cycles }: MTDPanelProps) {
  return (
    <section className="intel-card" aria-label="Moving target defense cycles">
      <div className="intel-card-header">
        <span className="intel-card-title" style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <Layers size={13} aria-hidden="true" style={{ color: "var(--text-muted)" }} />
          Moving Target Defense
        </span>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            color: "var(--text-muted)",
          }}
        >
          {cycles.length} cycle{cycles.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div style={{ padding: "12px 12px 12px" }}>
        {cycles.length === 0 ? (
          <div className="mtd-empty" role="status">
            Awaiting rotation trigger
          </div>
        ) : (
          <div className="mtd-timeline" role="list">
            {/* Column headers */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "56px minmax(0,1fr) auto",
                gap: "10px",
                padding: "0 12px 6px",
                fontSize: "9px",
                fontWeight: 700,
                letterSpacing: "0.07em",
                textTransform: "uppercase",
                color: "var(--text-disabled)",
              }}
              aria-hidden="true"
            >
              <span>CYCLE</span>
              <span>PORT RANGE</span>
              <span>SEED</span>
            </div>

            {cycles.map((cycle) => (
              <div className="mtd-cycle-row" key={cycle.id} role="listitem">
                <span className="mtd-cycle-id">#{cycle.id}</span>
                <span className="mtd-cycle-ports">{cycle.ports}</span>
                <span className="mtd-cycle-seed">{cycle.seed.slice(0, 8)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

/* ── Live Sandboxes & Honeytokens Panel ──────────────────────────────── */

interface LiveSandboxesProps {
  stats: {
    dockerCount:      number;
    honeytokensFired: number;
  };
}

export function LiveSandboxes({ stats }: LiveSandboxesProps) {
  return (
    <section className="intel-card" aria-label="Live sandboxes and honeytoken metrics">
      <div className="intel-card-header">
        <span className="intel-card-title" style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <Container size={13} aria-hidden="true" style={{ color: "var(--text-muted)" }} />
          Deception Assets
        </span>
      </div>

      <div className="sandbox-stats">
        {/* Live Sandboxes */}
        <div className="sandbox-stat" aria-label={`${stats.dockerCount} live sandboxes`}>
          <span className="sandbox-stat-label">Live Sandboxes</span>
          <span
            className="sandbox-stat-value"
            style={{ color: "var(--color-info)" }}
          >
            {stats.dockerCount}
          </span>
          <span className="sandbox-stat-sub">Containers active</span>
        </div>

        {/* Honeytokens */}
        <div className="sandbox-stat" aria-label={`${stats.honeytokensFired} honeytokens fired`}>
          <span className="sandbox-stat-label">Honeytokens Fired</span>
          <span
            className="sandbox-stat-value"
            style={{ color: stats.honeytokensFired > 0 ? "var(--color-critical)" : "var(--text-secondary)" }}
          >
            {stats.honeytokensFired}
          </span>
          <span className="sandbox-stat-sub">Credential traps</span>
        </div>
      </div>
    </section>
  );
}
