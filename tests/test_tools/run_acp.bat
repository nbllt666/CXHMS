@echo off
REM ACP 测试工具启动脚本
REM 以前台终端窗口方式启动 ACP 独立聊天客户端（Streamlit UI，端口 8502）
REM 前置条件：主系统后端已运行在 http://localhost:8001

cd /d "%~dp0\..\.."

echo ========================================
echo  ACP 独立聊天客户端
echo  UI: http://localhost:8502
echo  主系统: http://localhost:8001
echo  本节点 HTTP: http://localhost:8505
echo ========================================
echo.

python tests\test_tools\launch.py acp

echo.
echo ACP 测试工具已停止。
pause
