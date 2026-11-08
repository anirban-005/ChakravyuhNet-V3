import { useCallback, useEffect, useRef, useState } from "react";
import type { Intent } from "../types";

/* ─────────────────────────────────────────────────────────────────────────
   BUZZER ENGINE — Web Audio API synthesiser
   No audio files needed. Works in background tabs.
   ───────────────────────────────────────────────────────────────────────── */

type BuzzerTier = 1 | 2 | 3 | 4 | 5;

interface TierConfig {
  freqs:      number[];
  baseVolume: number;
  beepMs:     number;
  gapMs:      number;
  intervalMs: number;
  maxMs:      number;
  type:       "beep" | "siren";
}

const TIER_CONFIG: Record<BuzzerTier, TierConfig> = {
  1: { freqs: [440],           baseVolume: 0.15, beepMs: 100, gapMs: 0,   intervalMs: 5000, maxMs: 30_000,  type: "beep"  },
  2: { freqs: [660, 660],      baseVolume: 0.25, beepMs: 80,  gapMs: 120, intervalMs: 3000, maxMs: 30_000,  type: "beep"  },
  3: { freqs: [880, 880, 880], baseVolume: 0.35, beepMs: 60,  gapMs: 90,  intervalMs: 2000, maxMs: 45_000,  type: "beep"  },
  4: { freqs: [1000],          baseVolume: 0.55, beepMs: 80,  gapMs: 0,   intervalMs: 600,  maxMs: 60_000,  type: "beep"  },
  5: { freqs: [400, 1400],     baseVolume: 0.80, beepMs: 600, gapMs: 100, intervalMs: 700,  maxMs: 120_000, type: "siren" },
};

const INTENT_TIER: Record<Intent, BuzzerTier> = {
  camouflage: 1,
  snooping:   2,
  movement:   3,
  aggressive: 4,
  weapon:     5,
};

/* ── Low-level audio helpers ─────────────────────────────────────────── */

function scheduleBeep(
  ctx: AudioContext, freq: number, startSec: number,
  durationSec: number, volume: number,
): void {
  const osc  = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.type = "square";
  osc.frequency.setValueAtTime(freq, startSec);
  const attack = 0.005, release = 0.008;
  gain.gain.setValueAtTime(0, startSec);
  gain.gain.linearRampToValueAtTime(volume, startSec + attack);
  gain.gain.setValueAtTime(volume, startSec + durationSec - release);
  gain.gain.linearRampToValueAtTime(0, startSec + durationSec);
  osc.start(startSec);
  osc.stop(startSec + durationSec + 0.01);
}

function scheduleSiren(
  ctx: AudioContext, freqLow: number, freqHigh: number,
  startSec: number, durationSec: number, volume: number,
): void {
  const osc  = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.type = "sawtooth";
  osc.frequency.setValueAtTime(freqLow, startSec);
  osc.frequency.linearRampToValueAtTime(freqHigh,      startSec + durationSec * 0.65);
  osc.frequency.linearRampToValueAtTime(freqLow + 250, startSec + durationSec);
  const attack = 0.010, release = 0.025;
  gain.gain.setValueAtTime(0, startSec);
  gain.gain.linearRampToValueAtTime(volume, startSec + attack);
  gain.gain.setValueAtTime(volume, startSec + durationSec - release);
  gain.gain.linearRampToValueAtTime(0, startSec + durationSec);
  osc.start(startSec);
  osc.stop(startSec + durationSec + 0.01);
}

function fireBurst(ctx: AudioContext, tier: BuzzerTier, volume: number): void {
  const cfg = TIER_CONFIG[tier];
  const now = ctx.currentTime;
  if (cfg.type === "siren") {
    scheduleSiren(ctx, cfg.freqs[0], cfg.freqs[1], now, cfg.beepMs / 1000, volume);
    return;
  }
  let cursor = now;
  for (let i = 0; i < cfg.freqs.length; i++) {
    scheduleBeep(ctx, cfg.freqs[i], cursor, cfg.beepMs / 1000, volume);
    cursor += cfg.beepMs / 1000;
    if (i < cfg.freqs.length - 1) cursor += cfg.gapMs / 1000;
  }
}

/* ── Public interface ────────────────────────────────────────────────── */

export interface BuzzerEngine {
  armed:              boolean;
  activeTier:         BuzzerTier | null;
  arm:                () => void;
  triggerAlert:       (intent: Intent, riskScore?: number) => void;
  triggerSystemAlert: (module: string) => void;
  triggerVaultAlarm:  () => void;
  stopAll:            () => void;
}

export type { BuzzerTier };

/* ── Hook ────────────────────────────────────────────────────────────── */

export function useBuzzerEngine(): BuzzerEngine {
  const ctxRef          = useRef<AudioContext | null>(null);
  const intervalRef     = useRef<ReturnType<typeof setInterval> | null>(null);
  const maxTimerRef     = useRef<ReturnType<typeof setTimeout>  | null>(null);
  const activeTierRef   = useRef<BuzzerTier | null>(null);
  const volumeRef       = useRef(0.5);
  const armedRef        = useRef(false);
  // Pending tier: queued while AudioContext is still suspended
  const pendingTierRef  = useRef<{ tier: BuzzerTier; riskScore: number } | null>(null);

  const [armed,      setArmed]      = useState(false);
  const [activeTier, setActiveTier] = useState<BuzzerTier | null>(null);

  useEffect(() => { armedRef.current = armed; }, [armed]);

  /* ── stopAll ──────────────────────────────────────────────────────── */
  const stopAll = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (maxTimerRef.current) clearTimeout(maxTimerRef.current);
    intervalRef.current   = null;
    maxTimerRef.current   = null;
    activeTierRef.current = null;
    pendingTierRef.current = null;
    setActiveTier(null);
  }, []);

  /* ── activateTier ─────────────────────────────────────────────────── */
  const activateTier = useCallback((tier: BuzzerTier, riskScore: number) => {
    const ctx = ctxRef.current;
    if (!ctx) return;

    // If suspended: queue the tier and kick off a resume.
    // The statechange listener below will flush it when running.
    if (ctx.state === "suspended") {
      pendingTierRef.current = { tier, riskScore };
      ctx.resume().catch(() => {});
      return;
    }

    // Clear any existing pattern
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (maxTimerRef.current) clearTimeout(maxTimerRef.current);

    activeTierRef.current  = tier;
    pendingTierRef.current = null;
    setActiveTier(tier);

    const riskMod  = riskScore < 40 ? 0.70 : riskScore >= 70 ? 1.25 : 1.0;
    const speedMod = riskScore < 40 ? 1.30 : riskScore >= 70 ? 0.75 : 1.0;
    const cfg      = TIER_CONFIG[tier];
    const vol      = Math.min(cfg.baseVolume * riskMod, 0.95);
    const interval = Math.round(cfg.intervalMs * speedMod);
    volumeRef.current = vol;

    fireBurst(ctx, tier, vol);

    intervalRef.current = setInterval(() => {
      if (ctxRef.current && ctxRef.current.state === "running") {
        fireBurst(ctxRef.current, tier, volumeRef.current);
      }
    }, interval);

    maxTimerRef.current = setTimeout(stopAll, cfg.maxMs);
  }, [stopAll]);

  /* ── arm ──────────────────────────────────────────────────────────── */
  const arm = useCallback(() => {
    if (ctxRef.current) {
      if (ctxRef.current.state === "suspended") {
        ctxRef.current.resume().catch(() => {});
      }
      if (!armedRef.current) { setArmed(true); armedRef.current = true; }
      return;
    }
    try {
      const ctx = new AudioContext();
      ctxRef.current = ctx;
      setArmed(true);
      armedRef.current = true;

      // When the context becomes "running" (after resume or on creation),
      // flush any tier that was queued while it was suspended.
      ctx.addEventListener("statechange", () => {
        if (ctx.state === "running" && pendingTierRef.current) {
          const { tier, riskScore } = pendingTierRef.current;
          pendingTierRef.current = null;
          activateTier(tier, riskScore);
        }
      });
    } catch {
      /* AudioContext not available — silent fail */
    }
  }, [activateTier]);

  /* ── Auto-arm on first page interaction ──────────────────────────── */
  useEffect(() => {
    const onInteraction = () => { if (!armedRef.current) arm(); };
    document.addEventListener("click",   onInteraction, { once: true });
    document.addEventListener("keydown", onInteraction, { once: true });
    return () => {
      document.removeEventListener("click",   onInteraction);
      document.removeEventListener("keydown", onInteraction);
    };
  }, [arm]);

  /* ── Public triggers ─────────────────────────────────────────────── */

  const triggerAlert = useCallback((intent: Intent, riskScore = 50) => {
    // Try to arm silently if not yet armed (works after any prior page interaction)
    if (!armedRef.current) {
      arm();
      // If still not armed (no prior gesture at all), bail
      if (!armedRef.current) return;
    }
    // Every sequential command plays its own characteristic sound immediately.
    // No "never downgrade" guard — curl→siren, ssh→triple-beep, nmap→rapid-beep
    // each replace the previous pattern so the operator hears each threat.
    activateTier(INTENT_TIER[intent], riskScore);
  }, [activateTier, arm]);

  const triggerSystemAlert = useCallback((module: string) => {
    if (!armedRef.current) { arm(); if (!armedRef.current) return; }
    // Guard alerts (network pings, etc.) don't override intent alarms —
    // only escalate if there's currently nothing louder playing.
    const tier: BuzzerTier = module.toUpperCase() === "INTEGRITY" ? 4 : 2;
    if (activeTierRef.current !== null && activeTierRef.current >= tier) return;
    activateTier(tier, 60);
  }, [activateTier, arm]);

  const triggerVaultAlarm = useCallback(() => {
    if (!armedRef.current) { arm(); if (!armedRef.current) return; }
    activateTier(5, 100);
  }, [activateTier, arm]);

  /* ── Cleanup ──────────────────────────────────────────────────────── */
  useEffect(() => {
    return () => {
      stopAll();
      ctxRef.current?.close().catch(() => {});
    };
  }, [stopAll]);

  return { armed, activeTier, arm, triggerAlert, triggerSystemAlert, triggerVaultAlarm, stopAll };
}
