@echo off
chcp 65001 >nul
echo 启动 MCP 测试工具 (端口 8504)
echo.

C:\ProgramData\Anaconda3\python.exe -B -m streamlit run tests\test_tools\mcp\app.py --server.port 8504 --server.headless true

pause
