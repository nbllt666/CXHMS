@echo off
chcp 437 >nul
cls
title CXHMS - Frontend with Control Service (System)

echo ==========================================
echo    CXHMS - Chenxi Humanized Memory System
echo ==========================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo [INFO] Checking Python...

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found!
    pause
    exit /b 1
)

echo [OK] Python found.

echo.
echo [1/2] Starting Control Service in new window...
echo    URL: http://localhost:8765

start "CXHMS Control Service" cmd.exe /k "cd /d %SCRIPT_DIR% && python backend\control_service.py"

echo [OK] Control Service starting...

timeout /t 3 /nobreak >nul

echo.
echo [2/2] Starting Frontend...
echo    URL: http://localhost:5173
echo.
echo Press Ctrl+C to stop frontend.
echo.

cd frontend
call npm run dev
