@echo off
chcp 65001

REM Clear proxy settings
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set NUMEXPR_MAX_THREADS=16

echo ========================================
echo    CXHMS Backend Startup (Conda)
echo ========================================
echo.

SET CONDA_PATH=.\Miniconda3

REM Check if Conda exists
if not exist "%CONDA_PATH%\Scripts\activate.bat" (
    echo Error: Conda environment not found!
    echo Please use "3.启动后端(系统环境).bat" instead
    pause
    exit /b 1
)

REM Activate base environment
CALL %CONDA_PATH%\Scripts\activate.bat %CONDA_PATH%

SET KMP_DUPLICATE_LIB_OK=TRUE

echo Starting backend with Conda environment...
echo Access: http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo.

python main.py

pause
