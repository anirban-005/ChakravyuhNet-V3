from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import sys
from pathlib import Path

# Fix sys.path so 'app' is recognized as a package when run directly
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from app.models import CommandRequest
from app.simulation import SimulationEngine
import argparse
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

# Setup logging
log_dir = Path(r"C:\ProgramData\Antigravity\logs")
log_dir.mkdir(parents=True, exist_ok=True)

try:
    handlers = [logging.FileHandler(log_dir / "agent.log")]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
        
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
except PermissionError:
    # Fallback to local logging if not running as Administrator
    local_log_dir = Path(__file__).resolve().parent.parent / "logs"
    local_log_dir.mkdir(parents=True, exist_ok=True)
    
    handlers = [logging.FileHandler(local_log_dir / "maze.log")]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
        
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

logger = logging.getLogger("AntigravityAgent")


# Background guard tasks (started at server boot)
_guard_tasks: list[asyncio.Task] = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start embedded guard agents when the server boots."""
    from app.modules.guard_integrity import start_integrity_guard
    from app.modules.guard_network import start_network_guard
    t1 = asyncio.create_task(start_integrity_guard())
    t2 = asyncio.create_task(start_network_guard())
    _guard_tasks.extend([t1, t2])
    logger.info("Embedded guards started: IntegrityGuard + NetworkGuard")
    yield
    for t in _guard_tasks:
        t.cancel()
    logger.info("Guards stopped.")


BASE_DIR = Path(__file__).resolve().parents[1]
engine = SimulationEngine(
    vault_dir=BASE_DIR / "vault",
    reports_dir=BASE_DIR / "reports",
)

app = FastAPI(
    title="ChakravyuhNet API",
    description="Safe local demo backend for a shape-shifting honeypot.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/state")
async def get_state():
    return await engine.snapshot()


@app.post("/api/scenario/start")
async def start_scenario():
    return await engine.start_scenario()


@app.post("/api/scenario/reset")
async def reset_scenario():
    return await engine.reset()


@app.post("/api/shell/command")
async def run_command(payload: CommandRequest):
    return await engine.run_command(payload.command)


@app.post("/api/payload/upload")
async def upload_payload(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded payload was empty.")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Demo vault limit is 10 MB.")

    entry, state = await engine.capture_payload(
        filename=file.filename or "payload.bin",
        content=content,
        content_type=file.content_type,
    )
    return {"payload": entry, "state": state}


@app.get("/api/reports/latest")
async def latest_report():
    state = await engine.snapshot()
    if not state.latest_report:
        raise HTTPException(status_code=404, detail="No report has been generated yet.")
    return state.latest_report


@app.get("/api/reports/{report_id}/stix")
async def download_stix(report_id: str):
    state = await engine.snapshot()
    report = state.latest_report
    if not report or report.report_id != report_id:
        raise HTTPException(status_code=404, detail="Report not found.")
    return FileResponse(
        report.stix_path,
        media_type="application/stix+json",
        filename=f"{report_id}.stix.json",
    )


@app.get("/api/reports/{report_id}/pdf")
async def download_pdf(report_id: str):
    state = await engine.snapshot()
    report = state.latest_report
    if not report or report.report_id != report_id or not report.pdf_path:
        raise HTTPException(status_code=404, detail="Report not found.")
    return FileResponse(
        report.pdf_path,
        media_type="application/pdf",
        filename=f"{report_id}.pdf",
    )


@app.websocket("/ws/events")
async def event_stream(websocket: WebSocket):
    import asyncio
    from fastapi import WebSocketDisconnect
    await websocket.accept()
    queue = await engine.subscribe()
    try:
        while True:
            # Race: new event to push vs. client message/disconnect
            get_task = asyncio.create_task(queue.get())
            receive_task = asyncio.create_task(websocket.receive_bytes())

            done, pending = await asyncio.wait(
                [get_task, receive_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            if receive_task in done:
                # Check if it's a real disconnect or just a ping frame
                try:
                    data = receive_task.result()
                    # WebSocket ping/pong are handled by the library automatically
                    # Any non-empty bytes from the browser is a close frame or text
                    # We only break on actual disconnection (receive raises exception)
                except Exception:
                    # Exception means the client disconnected
                    for task in pending:
                        task.cancel()
                    break
                # Otherwise it was a ping — cancel get_task and loop again
                if get_task in pending:
                    get_task.cancel()
                continue

            if get_task in done:
                event = get_task.result()
                try:
                    await websocket.send_json(event)
                except Exception:
                    break
                if receive_task in pending:
                    receive_task.cancel()
    except Exception as e:
        logger.info(f"WebSocket client disconnected: {e}")
    finally:
        await engine.unsubscribe(queue)

from fastapi import Request
from fastapi.responses import JSONResponse
import traceback

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    with open('error.log', 'w') as f:
        f.write(traceback.format_exc())
    return JSONResponse(status_code=500, content={'detail': str(exc)})

class AlertPayload(BaseModel):
    module: str
    message: str
    details: dict

@app.post("/api/alerts")
async def receive_alert(payload: AlertPayload):
    # Broadcast the guard alert to all WebSocket clients for display in the Guard Alerts panel.
    await engine.broadcast_event(
        event_type="system_alert",
        message=payload.message,
        data={
            "module":  payload.module,
            "message": payload.message,
            "details": payload.details,
        },
    )

    # ── Fusion: real OS offensive-tool detections → simulation engine ──────
    # When the integrity guard detects a genuinely suspicious tool (nmap, curl,
    # ssh, etc.) being run on the host, feed it into the AI brain as if the
    # attacker issued the command.  This makes the simulation react to real
    # activity without needing the operator to type in the terminal manually.
    #
    # Safety net: common admin shells are explicitly blocked here as a
    # defence-in-depth measure — they are already excluded from SUSPICIOUS in
    # guard_integrity.py, but we double-check so a future config change can
    # never accidentally cause false attacker entries.
    _SHELL_BLOCKLIST = {"powershell", "cmd", "pwsh", "explorer", "python", "node"}

    if (
        payload.module.lower() in ("integrity", "integrityguard")
        and "Suspicious process detected:" in payload.message
    ):
        try:
            # Extract bare process name: "curl.exe (PID: 123) …" → "curl"
            raw = payload.message.split("detected:")[1].strip().split()[0]
            proc_name = raw.replace(".exe", "").lower()

            if proc_name not in _SHELL_BLOCKLIST:
                logger.info(f"Fusion: injecting real process '{proc_name}' into simulation")
                await engine.run_command(proc_name)
        except Exception as e:
            logger.error(f"Fusion injection failed: {e}")

    return {"status": "ok"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dual-Mode Orchestrator")
    parser.add_argument("--mode", choices=["maze", "guard"], default="maze", help="Run mode")
    parser.add_argument("--install", action="store_true", help="Install the background service")
    parser.add_argument("--service", action="store_true", help="Run as a Windows Service (invoked by SCM)")
    args = parser.parse_args()

    if args.install:
        logger.info("Starting installation...")
        from app.installer import install_service
        install_service()
        sys.exit(0)

    if args.mode == "maze":
        logger.info("Starting in MAZE mode (C2 Dashboard & Deception)...")
        import uvicorn
        uvicorn.run("app.main:app", host="127.0.0.1", port=8001, reload=False)
    elif args.mode == "guard":
        if args.service:
            import win32serviceutil
            import win32service
            import win32event
            import servicemanager
            
            class AntigravityGuardService(win32serviceutil.ServiceFramework):
                _svc_name_ = "AntigravityAgent"
                _svc_display_name_ = "Antigravity Security Agent"
                
                def __init__(self, args):
                    win32serviceutil.ServiceFramework.__init__(self, args)
                    self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
                    
                def SvcStop(self):
                    self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
                    win32event.SetEvent(self.hWaitStop)
                    
                def SvcDoRun(self):
                    servicemanager.LogMsg(
                        servicemanager.EVENTLOG_INFORMATION_TYPE,
                        servicemanager.PYS_SERVICE_STARTED,
                        (self._svc_name_, '')
                    )
                    self.main()
                    
                def main(self):
                    logger.info("Guard Service Framework Initialized.")
                    from app.modules.guard_integrity import start_integrity_guard
                    from app.modules.guard_network import start_network_guard
                    
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    async def run_guards():
                        task1 = asyncio.create_task(start_integrity_guard())
                        task2 = asyncio.create_task(start_network_guard())
                        
                        while True:
                            rc = win32event.WaitForSingleObject(self.hWaitStop, 1000)
                            if rc == win32event.WAIT_OBJECT_0:
                                logger.info("Service stop signal received.")
                                break
                            await asyncio.sleep(0.1)
                            
                    loop.run_until_complete(run_guards())
                    
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(AntigravityGuardService)
            servicemanager.StartServiceCtrlDispatcher()
        else:
            logger.info("Starting in GUARD mode (Console)...")
            from app.modules.guard_integrity import start_integrity_guard
            from app.modules.guard_network import start_network_guard
            
            async def run_guards():
                task1 = asyncio.create_task(start_integrity_guard())
                task2 = asyncio.create_task(start_network_guard())
                await asyncio.gather(task1, task2)
                
            try:
                asyncio.run(run_guards())
            except KeyboardInterrupt:
                logger.info("Guard mode stopped.")
            except Exception as e:
                logger.exception("Guard mode crashed: %s", e)
