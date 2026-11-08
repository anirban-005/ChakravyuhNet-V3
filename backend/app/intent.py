"""Intent classification engine for ChakravyuhNet.

Every command the attacker types is classified into exactly one of five
"intent buckets."  The bucket determines *what the map does*, completely
independent of the text the terminal shows.  This lets us add hundreds of
new commands in the future just by dropping patterns into the right bucket.

Buckets (highest priority → lowest):
  1. weapon     – payload delivery / execution      → triggers vault capture
  2. aggressive – scanning / enumeration             → activates tarpit swarm
  3. movement   – lateral movement to another host   → spawns decoy node
  4. snooping   – reading secrets / sensitive data   → pulses active node
  5. camouflage – harmless info-gathering            → no map change
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Intent = Literal["camouflage", "snooping", "movement", "aggressive", "weapon"]
MapAction = Literal["none", "pulse", "spawn_decoy", "tarpit", "vault"]


@dataclass(frozen=True)
class IntentResult:
    """Classification of a single attacker command."""

    intent: Intent
    label: str          # human-readable description shown in the UI
    map_action: MapAction
    brain_message: str  # logged in the AI Brain Log panel
    brain_level: Literal["info", "warn", "alert"] = "info"


# ── Pattern banks (evaluated top → bottom, first match wins) ─────────

_WEAPON_PATTERNS: list[re.Pattern[str]] = [re.compile(p, re.IGNORECASE) for p in [
    r"\bwget\b",
    r"\bcurl\b",
    r"\bchmod\s+\+x\b",
    r"^\./",                         # ./exploit.sh
    r"\bpython[23]?\s+\S+\.py\b",
    r"\bbash\s+\S+",
    r"\bsh\s+\S+",
    r"\bperl\s+",
    r"\bruby\s+",
    r"\bpowershell\b",
    r"\bcertutil\b",
    r"\bmsfvenom\b",
    r"\bmsfconsole\b",
    r"\breverse.?shell\b",
    r"\bbind.?shell\b",
    r"\bdropper\b",
    r"\bimplant\b",
    r"\bbeacon\b",
    r"\bcobalt\b",
    r"\bempire\b",
    r"\bpayload\b",
    r"\bnc\s+-[elvp]",
    r"\bnetcat\b.*-[elvp]",
    r"\bsudo\b",
    r"\bbase64\s+-d\b",               # decode + pipe – typical staging
    r"\bmkfifo\b",                     # named-pipe reverse shell
]]

_AGGRESSIVE_PATTERNS: list[re.Pattern[str]] = [re.compile(p, re.IGNORECASE) for p in [
    r"\bnmap\b",
    r"\bping\b",
    r"\btraceroute\b",
    r"\btracert\b",
    r"\bmasscan\b",
    r"\bdirb\b",
    r"\bdirbuster\b",
    r"\bgobuster\b",
    r"\bnikto\b",
    r"\bsqlmap\b",
    r"\bhydra\b",
    r"\bmedusa\b",
    r"\benum4linux\b",
    r"\bsmbclient\b",
    r"\brpcclient\b",
    r"\bsnmpwalk\b",
    r"\bwpscan\b",
    r"\bnuclei\b",
    r"\bffuf\b",
    r"\bferoxbuster\b",
    r"\brushscan\b",
    r"\bzmap\b",
    r"\barp\s+-a\b",
    r"\barpwatch\b",
]]

_MOVEMENT_PATTERNS: list[re.Pattern[str]] = [re.compile(p, re.IGNORECASE) for p in [
    r"\bssh\b",
    r"\bscp\b",
    r"\bsftp\b",
    r"\bftp\b",
    r"\btelnet\b",
    r"\brsh\b",
    r"\brdesktop\b",
    r"\bxfreerdp\b",
    r"\bpsexec\b",
    r"\bwmic?\b",
    r"\bsocat\b",
    r"\bchisel\b",
    r"\bpivot\b",
    r"\bproxy.*chain\b",
    r"\btunnel\b",
]]

_SNOOPING_PATTERNS: list[re.Pattern[str]] = [re.compile(p, re.IGNORECASE) for p in [
    r"\bcat\s+\.env\b",
    r"\bcat\s+/etc/passwd\b",
    r"\bcat\s+/etc/shadow\b",
    r"\bcat\s+.*config",
    r"\bcat\s+.*\.key\b",
    r"\bcat\s+.*\.pem\b",
    r"\bcat\s+~/\.ssh/",
    r"\bcat\s+~/\.bash_history\b",
    r"\bgrep\b.*(?:password|secret|key|token|credential|api.?key)",
    r"\bfind\b.*(?:\.key|\.pem|\.env|secret|password|credential)",
    r"\bhistory\b",
    r"\bprintenv\b",
    r"\bstrings\b",
    r"\bxxd\b",
    r"\bopenssl\b",
    r"\bcat\s+/etc/hosts\b",
    r"\benv\b",
    r"\bcat\s+.*ledger",
    r"\bcat\s+.*\.db\b",
    r"\bsqlite3?\b",
]]


def classify(command: str) -> IntentResult:
    """Classify a shell command into one of the five intent buckets.

    Pattern lists are checked in threat-priority order.
    First match wins – no command can belong to two buckets.
    """
    stripped = command.strip()

    # ── Weapon (highest threat) ──────────────────────────────────────
    for pattern in _WEAPON_PATTERNS:
        if pattern.search(stripped):
            verb = stripped.split()[0]
            return IntentResult(
                intent="weapon",
                label="Payload Delivery",
                map_action="vault",
                brain_message=(
                    f"WEAPON DETECTED: '{verb}' — payload staging/execution "
                    f"attempt.  Trapdoor engaged.  Vault capture sequence initiated."
                ),
                brain_level="alert",
            )

    # ── Aggressive ───────────────────────────────────────────────────
    for pattern in _AGGRESSIVE_PATTERNS:
        if pattern.search(stripped):
            verb = stripped.split()[0]
            return IntentResult(
                intent="aggressive",
                label="Active Scanning",
                map_action="tarpit",
                brain_message=(
                    f"Aggressive tool detected: '{verb}'.  "
                    f"Tarpit swarm activated — synthetic latency injected to degrade tool accuracy."
                ),
                brain_level="warn",
            )

    # ── Movement ─────────────────────────────────────────────────────
    for pattern in _MOVEMENT_PATTERNS:
        if pattern.search(stripped):
            return IntentResult(
                intent="movement",
                label="Lateral Movement",
                map_action="spawn_decoy",
                brain_message=(
                    f"Lateral movement attempt via '{stripped.split()[0]}'.  "
                    f"RL policy spawning decoy infrastructure along predicted attacker path."
                ),
                brain_level="alert",
            )

    # ── Snooping ─────────────────────────────────────────────────────
    for pattern in _SNOOPING_PATTERNS:
        if pattern.search(stripped):
            return IntentResult(
                intent="snooping",
                label="Secret Harvesting",
                map_action="pulse",
                brain_message=(
                    f"Sensitive data access: '{stripped.split()[0]}' targeting secrets.  "
                    f"Serving honeytokens.  Node telemetry pulse triggered."
                ),
                brain_level="warn",
            )

    # ── Camouflage (default) ─────────────────────────────────────────
    return IntentResult(
        intent="camouflage",
        label="Reconnaissance",
        map_action="none",
        brain_message=(
            f"Benign reconnaissance: '{stripped.split()[0] if stripped else 'empty'}'.  "
            f"Serving plausible fake output.  No topology change required."
        ),
        brain_level="info",
    )
