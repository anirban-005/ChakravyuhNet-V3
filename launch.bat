@echo off
:: ========================================================
:: AntigravityAgent Deployment Script (Directory Mode)
:: ========================================================

net session >nul 2>&1
if %errorLevel% == 0 (
    goto :admin_mode
) else (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:admin_mode
if not exist "%~dp0AntigravityAgent\AntigravityAgent.exe" (
    echo [ERROR] Not found. Did you move the AntigravityAgent folder into the root?
    pause
    exit /b
)

echo [i] Starting installation...
"%~dp0AntigravityAgent\AntigravityAgent.exe" --install

echo [i] Installation complete!
pause