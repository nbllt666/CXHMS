@echo off
chcp 936 >nul
cls
title CXHMS - Frontend with Control Service (System)

echo ==========================================
echo    CXHMS - Chenxi Humanized Memory System
echo ==========================================
echo.

REM Clean environment variables
set XY=
set OXY=
set xy=
set oxy=
set MAX_THREADS=
set S=
set ONDA_PATH=
set f=
set or=
set ase=

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo [1/2] Starting Control Service...
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
