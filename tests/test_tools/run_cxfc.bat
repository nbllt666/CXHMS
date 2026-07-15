@echo off
REM CXFC 测试工具启动脚本
REM 以前台终端窗口方式启动 CXFC 测试工具（Streamlit UI，端口 8501）
REM 前置条件：主系统后端已运行在 http://localhost:8001

cd /d "%~dp0\..\.."

echo ========================================
echo  CXFC 测试工具
echo  UI: http://localhost:8501
echo  主系统: http://localhost:8001
echo ========================================
echo.

python tests\test_tools\launch.py cxfc

echo.
echo CXFC 测试工具已停止。
pause
