import { Square, Volume2 } from "lucide-react";
import type { BuzzerEngine, BuzzerTier } from "../hooks/useBuzzerEngine";

/* ─────────────────────────────────────────────────────────────────────────
   BUZZER INDICATOR — Topbar audio alarm status widget
   ARM button → idle "ARMED" label → active tier badge + STOP button
   ───────────────────────────────────────────────────────────────────────── */

const TIER_LABELS: Record<BuzzerTier, string> = {
  1: "LOW",
  2: "LOW-MED",
  3: "MEDIUM",
  4: "HIGH",
  5: "CRITICAL",
};

const TIER_COLORS: Record<BuzzerTier, string> = {
  1: "#10B981",
  2: "#F59E0B",
  3: "#F97316",
  4: "#EF4444",
  5: "#FF1744",
};

interface BuzzerIndicatorProps {
  engine: BuzzerEngine;
}

export function BuzzerIndicator({ engine }: BuzzerIndicatorProps) {
  const { armed, activeTier, arm, stopAll } = engine;

  /* ── Not yet armed — show ARM button ── */
  if (!armed) {
    return (
      <div className="buzzer-widget" aria-label="Audio alarm system — not armed">
        <button
          type="button"
          className="buzzer-arm-btn"
          onClick={arm}
          title="Click to arm audio threat alerts"
          id="btn-arm-audio"
        >
          <Volume2 size={13} aria-hidden="true" />
          <span>ARM AUDIO</span>
        </button>
      </div>
    );
  }

  const color = activeTier ? TIER_COLORS[activeTier] : undefined;

  return (
    <div
      className="buzzer-widget buzzer-widget--armed"
      aria-label={`Audio alarm: ${activeTier ? TIER_LABELS[activeTier] : "idle"}`}
    >
      {/* Animated speaker icon */}
      <div
        className={`buzzer-speaker${activeTier ? " buzzer-speaker--active" : ""}`}
        style={color ? ({ "--buzzer-color": color } as React.CSSProperties) : undefined}
        aria-hidden="true"
      >
        <Volume2 size={14} />
        {activeTier && (
          <>
            <span className="buzzer-ring buzzer-ring--1" />
            <span className="buzzer-ring buzzer-ring--2" />
          </>
        )}
      </div>

      {/* Tier badge — shows threat level when active */}
      {activeTier ? (
        <span
          className="buzzer-tier-badge"
          aria-label={`Alarm tier: ${TIER_LABELS[activeTier]}`}
          style={{
            color,
            borderColor: color ? `${color}55` : undefined,
            background:  color ? `${color}18` : undefined,
            cursor: "default",
          }}
        >
          ▶ {TIER_LABELS[activeTier]}
        </span>
      ) : (
        <span className="buzzer-idle-label" aria-label="Armed and monitoring">
          ARMED
        </span>
      )}

      {/* STOP button — only visible when alarm is ringing */}
      {activeTier && (
        <button
          type="button"
          className="buzzer-stop-btn"
          onClick={stopAll}
          title="Stop alarm"
          aria-label="Stop alarm"
          id="btn-buzzer-stop"
        >
          <Square size={10} fill="currentColor" aria-hidden="true" />
          STOP
        </button>
      )}
    </div>
  );
}
