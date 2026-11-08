# Set Execution Policy just for this process to ensure scripts run
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force

Write-Host "--- Initializing ChakravyuhNet v2 Ecosystem ---" -ForegroundColor Cyan

# ── Paths ──────────────────────────────────────────────────────────────
$backendPath  = "D:\ChakravuhaNet\backend"
$frontendPath = "D:\ChakravuhaNet\frontend"
$python       = "$backendPath\.venv\Scripts\python.exe"

# ── 1. Start AI Brain (Ollama) ─────────────────────────────────────────
Write-Host "[1/3] Launching AI Brain (Ollama)..." -ForegroundColor Yellow
Start-Process ollama -ArgumentList "serve" -WindowStyle Minimized

# ── 2. Start Backend (FastAPI / uvicorn) ───────────────────────────────
Write-Host "[2/3] Launching Backend Server..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$backendPath'; & '$python' -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload"
)

# ── 3. Start Frontend (Vite / React) ──────────────────────────────────
Write-Host "[3/3] Launching Frontend Dashboard..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$frontendPath'; npm run dev"
)

# ── 4. Wait for services to fully bind their ports ────────────────────
Write-Host "Waiting for services to stabilize (10s)..." -ForegroundColor Gray
Start-Sleep -Seconds 10

# ── 5. Launch Browser ─────────────────────────────────────────────────
Write-Host "System Online. Launching Dashboard!" -ForegroundColor Green
Start-Process "http://localhost:5173"