# ChakravyuhNet

An AI-driven, shape-shifting honeypot demo that traps attackers inside an isolated deception maze, captures their behavior, and exports threat intelligence.

This repository contains a safe local prototype for demos and judging:

- FastAPI backend with WebSocket event streaming.
- React dashboard with hacker-side and AI-side views.
- Dynamic decoy topology simulation.
- LLM-style fake Linux shell responses, with optional Ollama integration.
- Safe payload vaulting with SHA-256 hashing.
- STIX 2.1 JSON and PDF-style incident report generation.

The default build is intentionally defensive and local. It simulates tarpitting and tool poisoning instead of sending harmful payloads, ZIP bombs, or traffic to third-party systems.

## Quick Start

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

If `npm` is not available on this Windows machine, the local environment used
for verification can be recreated with:

```powershell
cd frontend
..\backend\.venv\Scripts\python.exe -m pip install nodeenv
..\backend\.venv\Scripts\python.exe -m nodeenv .nodeenv --node=lts --prebuilt
$env:Path = (Resolve-Path '.\.nodeenv\Scripts').Path + ';' + $env:Path
.\.nodeenv\Scripts\npm.cmd install
.\.nodeenv\Scripts\npm.cmd run dev
```

Open the Vite URL, usually:

```text
http://localhost:5173
```

## Optional Ollama Shell Illusion

The fake shell works without an LLM. To use Ollama for richer command output:

```powershell
$env:OLLAMA_BASE_URL="http://127.0.0.1:11434"
$env:OLLAMA_MODEL="llama3.1:8b"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend falls back to deterministic fake shell output if Ollama is unavailable.

## API Highlights

- `GET /api/state` returns the current glass-box dashboard state.
- `POST /api/scenario/start` runs a scripted attacker encounter.
- `POST /api/scenario/reset` resets the maze.
- `POST /api/shell/command` sends a fake terminal command into the deception engine.
- `POST /api/payload/upload` stores a payload safely in the local vault.
- `GET /api/reports/latest` returns the latest generated incident report metadata.
- `GET /api/reports/{report_id}/stix` downloads STIX JSON.
- `GET /api/reports/{report_id}/pdf` downloads the PDF incident summary.
- `WS /ws/events` streams live state changes.

## Safety Boundaries

ChakravyuhNet's demo mode does not:

- exploit attackers,
- generate or deploy malware,
- create ZIP bombs,
- attack external scanners,
- run captured files,
- expose the honeypot to the public internet by default.

Captured uploads are stored inertly in `backend/vault` and represented in reports by metadata and hashes.

## Suggested Next Build Steps

1. Replace the scripted scenario with real event ingestion from an isolated lab network.
2. Add Docker SDK orchestration for disposable decoy containers.
3. Train a Gymnasium/SB3 policy against simulated attacker paths.
4. Add TAXII publishing behind an explicit allowlist.
5. Wire the shell listener to Paramiko inside a private test subnet.
