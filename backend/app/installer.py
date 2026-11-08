import os
import shutil
import sys
import subprocess
import win32serviceutil
import win32service
import win32event
import servicemanager
import logging

logger = logging.getLogger("AntigravityAgent.Installer")

def install_service():
    target_dir = r"C:\ProgramData\Antigravity"
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    logs_dir = os.path.join(target_dir, "logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    # 1. Determine executable path
    exe_path = sys.executable
    is_frozen = getattr(sys, 'frozen', False)
    
    if is_frozen:
        target_exe = exe_path
        logger.info(f"Using in-place executable: {target_exe}")
    else:
        logger.warning("Not running as a compiled exe. Testing mode.")
        target_exe = sys.executable
        # For testing from source, we might need the script path
        script_path = os.path.abspath(sys.argv[0])
        exe_args = f'"{script_path}" --mode guard'
        
    # 2. Register the service
    svc_name = "AntigravityAgent"
    svc_display_name = "Antigravity Security Agent"
    svc_description = "Background system integrity and network monitoring agent."
    
    # We want the service to run `AntigravityAgent.exe --mode guard --service`
    if is_frozen:
        bin_path = f'"{target_exe}" --mode guard --service'
    else:
        bin_path = f'"{target_exe}" "{script_path}" --mode guard --service'
        
    try:
        # Remove existing service if it exists
        subprocess.run(["sc", "stop", svc_name], capture_output=True)
        subprocess.run(["sc", "delete", svc_name], capture_output=True)
        
        # Create the service
        subprocess.run([
            "sc", "create", svc_name,
            "binPath=", bin_path,
            "start=", "auto",
            "DisplayName=", svc_display_name
        ], check=True)
        
        # Set description
        subprocess.run([
            "sc", "description", svc_name, svc_description
        ], check=True)
        
        # Set recovery rules: Restart Service on Failure (after 60000ms = 60s)
        subprocess.run([
            "sc", "failure", svc_name,
            "reset=", "86400",
            "actions=", "restart/60000/restart/60000/restart/60000"
        ], check=True)
        
        logger.info(f"Service '{svc_name}' installed successfully with self-healing recovery rules.")
        
        # Start the service
        subprocess.run(["sc", "start", svc_name], check=True)
        logger.info(f"Service '{svc_name}' started.")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"SC command failed: {e}")
    except Exception as e:
        logger.error(f"Failed to install service: {e}")
