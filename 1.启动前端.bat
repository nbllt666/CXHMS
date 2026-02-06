@echo off
chcp 65001 >nul

REM 清除代理设置
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=

echo ========================================
echo    CXHMS 前端启动脚本
echo ========================================
echo.

REM 检查 frontend 目录是否存在
if not exist "frontend\" (
    echo 错误：frontend 目录不存在！
    pause
    exit /b 1
)

cd frontend

REM 检查 node_modules 是否存在
if not exist "node_modules\" (
    echo 正在安装前端依赖...
    call npm install
    if errorlevel 1 (
        echo 安装依赖失败！
        pause
        exit /b 1
    )
)

echo 正在启动前端开发服务器...
echo 访问地址: http://localhost:3000
echo.

REM 启动前端
call npm run dev

pause
