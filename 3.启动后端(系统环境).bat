@echo off
chcp 65001

REM Clear proxy settings
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set NUMEXPR_MAX_THREADS=16

echo ========================================
echo    CXHMS Backend Startup (System)
echo ========================================
echo.

SET KMP_DUPLICATE_LIB_OK=TRUE

echo Starting backend with system Python...
echo Access: http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo.

python main.py

pause
