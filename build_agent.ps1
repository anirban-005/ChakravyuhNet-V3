# 1. Navigate to the backend directory
Set-Location -Path "D:\CKV_V2\ChakravuhaNet\backend"

# 2. Clean up previous corrupted PyInstaller builds (to prevent cached errors)
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "AntigravityAgent.spec") { Remove-Item -Force "AntigravityAgent.spec" }

# 3. Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# 4. Compile the agent using the optimized, crash-free PyInstaller command
pyinstaller --onefile --noconsole --hidden-import=win32timezone --collect-all stable_baselines3 --exclude-module torchaudio --exclude-module torchvision --exclude-module tensorflow --exclude-module tensorboard --name AntigravityAgent app\main.py

# 5. Move the compiled .exe to the root project folder
Move-Item -Path ".\dist\AntigravityAgent.exe" -Destination "D:\CKV_V2\ChakravuhaNet\" -Force

# 6. Print success message
Write-Host "Success! The .exe is now in your root folder. You can now double-click launch.bat!" -ForegroundColor Green
