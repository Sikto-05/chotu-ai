@echo off
title CHOTU AI — Installer
color 0B
echo.
echo  ========================================
echo    ⚡  CHOTU AI — Elite Personal Assistant
echo    Installation Script v1.0
echo  ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python is not installed or not in PATH.
    echo  Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [OK] Python %PYVER% detected.

:: Check pip
pip --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] pip not found. Please reinstall Python.
    pause
    exit /b 1
)

echo  [OK] pip found.
echo.
echo  Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo  [WARN] Could not create virtual environment. Using system Python.
) else (
    echo  [OK] Virtual environment created.
    call venv\Scripts\activate.bat
)

echo.
echo  Installing CHOTU AI dependencies...
echo  (This may take 3-5 minutes on first install)
echo.

pip install --upgrade pip --quiet
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo  [WARN] Some packages failed. Attempting individual installs...
    pip install google-generativeai
    pip install speech_recognition
    pip install edge-tts
    pip install pygame
    pip install customtkinter
    pip install Pillow
    pip install psutil
    pip install numpy
    pip install requests
    pip install beautifulsoup4
    pip install python-dotenv
    pip install pywin32
    pip install pyautogui
    pip install keyboard
    pip install pyttsx3
    pip install googlesearch-python
    pip install send2trash
    echo.
    echo  Note: pyaudio requires manual install on some systems.
    echo  If voice recording fails, run: pip install pyaudio
)

echo.
echo  [OK] Dependencies installed.

:: Create .env if not exists
if not exist ".env" (
    copy ".env.example" ".env" >nul 2>&1
    echo  [OK] Created .env configuration file.
    echo  [!] Please edit .env and add your GEMINI_API_KEY
)

:: Create data directories
mkdir data 2>nul
mkdir data\voice_samples 2>nul
mkdir memory 2>nul
echo  [OK] Data directories created.

:: Create desktop shortcut
echo  Creating desktop shortcut...
set SCRIPT_DIR=%~dp0
set SHORTCUT_PATH=%USERPROFILE%\Desktop\CHOTU AI.lnk
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT_PATH%'); $sc.TargetPath = 'pythonw.exe'; $sc.Arguments = 'main.py'; $sc.WorkingDirectory = '%SCRIPT_DIR%'; $sc.Description = 'CHOTU AI Personal Assistant'; $sc.Save()" >nul 2>&1
if exist "%SHORTCUT_PATH%" (
    echo  [OK] Desktop shortcut created.
) else (
    echo  [WARN] Could not create desktop shortcut.
)

:: Create batch launcher
echo @echo off > launch_chotu.bat
echo title CHOTU AI >> launch_chotu.bat
echo cd /d "%SCRIPT_DIR%" >> launch_chotu.bat
echo if exist "venv\Scripts\pythonw.exe" ( >> launch_chotu.bat
echo     venv\Scripts\pythonw.exe main.py >> launch_chotu.bat
echo ) else ( >> launch_chotu.bat
echo     pythonw main.py >> launch_chotu.bat
echo ) >> launch_chotu.bat
echo  [OK] Launcher created: launch_chotu.bat

echo.
echo  ========================================
echo   ✅  CHOTU AI Installation Complete!
echo  ========================================
echo.
echo  Next steps:
echo  1. Edit .env and add your GEMINI_API_KEY
echo     (Get free key: https://aistudio.google.com)
echo  2. Double-click "CHOTU AI" on your desktop
echo     OR run: python main.py
echo  3. Complete the setup wizard (first run only)
echo.
echo  Press any key to launch CHOTU AI now...
pause >nul

start "" python main.py
