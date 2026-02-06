@echo off
chcp 65001 >nul

REM 清除代理设置
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set NUMEXPR_MAX_THREADS=16

echo ========================================
echo    CXHMS 后端启动脚本 (系统环境)
echo ========================================
echo.

SET KMP_DUPLICATE_LIB_OK=TRUE

echo 正在使用系统 Python 启动后端服务...
echo 访问地址: http://localhost:8000
echo API文档: http://localhost:8000/docs
echo.

python main.py

pause
