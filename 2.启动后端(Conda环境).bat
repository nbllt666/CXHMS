@echo off
chcp 65001 >nul

REM 清除代理设置
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set NUMEXPR_MAX_THREADS=16

echo ========================================
echo    CXHMS 后端启动脚本 (Conda环境)
echo ========================================
echo.

SET CONDA_PATH=.\Miniconda3

REM 检查 Conda 是否存在
if not exist "%CONDA_PATH%\Scripts\activate.bat" (
    echo 错误：未找到 Conda 环境！
    echo 请使用 "3.启动后端(系统环境).bat" 启动
    pause
    exit /b 1
)

REM 激活base环境
CALL %CONDA_PATH%\Scripts\activate.bat %CONDA_PATH%

SET KMP_DUPLICATE_LIB_OK=TRUE

echo 正在使用 Conda 环境启动后端服务...
echo 访问地址: http://localhost:8000
echo API文档: http://localhost:8000/docs
echo.

python main.py

pause
