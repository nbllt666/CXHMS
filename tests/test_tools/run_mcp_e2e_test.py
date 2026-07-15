"""MCP 端到端验证脚本"""
import urllib.request
import json
import time
import sys
import os

# Wait for backend
base = 'http://localhost:8001'
for i in range(10):
    try:
        r = urllib.request.urlopen(f'{base}/acp/health', timeout=3)
        print(f'Backend ready: {r.status}')
        break
    except Exception:
        print(f'Waiting for backend... ({i+1}/10)')
        time.sleep(3)
else:
    print('Backend not ready, aborting')
    sys.exit(1)

# Start mock MCP server
_PROJECT_ROOT = os.getcwd()
_TESTS_TOOLS = os.path.join(_PROJECT_ROOT, 'tests', 'test_tools')
sys.path.insert(0, _TESTS_TOOLS)
sys.path.insert(0, _PROJECT_ROOT)
from mcp.mock_mcp_server import MockMCPServer

mock = MockMCPServer(host='127.0.0.1', port=8600)
result = mock.start()
print(f'Mock MCP server start: {result}')
time.sleep(1)

# Test mock MCP server directly
try:
    r = urllib.request.urlopen('http://127.0.0.1:8600/health', timeout=3)
    print(f'[OK] Mock MCP /health: {json.loads(r.read())}')
except Exception as e:
    print(f'[FAIL] Mock MCP /health: {e}')

try:
    r = urllib.request.urlopen('http://127.0.0.1:8600/tools', timeout=3)
    tools = json.loads(r.read())
    tool_count = len(tools.get('tools', []))
    print(f'[OK] Mock MCP /tools: {tool_count} tools')
except Exception as e:
    print(f'[FAIL] Mock MCP /tools: {e}')

try:
    req = urllib.request.Request('http://127.0.0.1:8600/call',
        data=json.dumps({'tool': 'echo', 'arguments': {'text': 'hello'}}).encode(),
        headers={'Content-Type': 'application/json'})
    r = urllib.request.urlopen(req, timeout=3)
    print(f'[OK] Mock MCP /call echo: {json.loads(r.read())}')
except Exception as e:
    print(f'[FAIL] Mock MCP /call echo: {e}')

print()
print('=== MCP Backend API Tests ===')

# 1. Add MCP server (HTTP mode)
try:
    payload = json.dumps({'name': 'test-mcp', 'command': '', 'args': [], 'env': {}, 'endpoint_url': 'http://127.0.0.1:8600'}).encode()
    req = urllib.request.Request(f'{base}/api/tools/mcp/servers', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    r = urllib.request.urlopen(req, timeout=5)
    data = json.loads(r.read())
    print(f'[OK] Add MCP server: status={data.get("status")}')
except Exception as e:
    print(f'[FAIL] Add MCP server: {e}')

# 2. Start MCP server (HTTP mode)
try:
    payload = json.dumps({'name': 'test-mcp'}).encode()
    req = urllib.request.Request(f'{base}/api/tools/mcp/servers/start', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    r = urllib.request.urlopen(req, timeout=15)
    data = json.loads(r.read())
    print(f'[OK] Start MCP server: {data.get("status")} - {data.get("message", "")}')
except Exception as e:
    print(f'[FAIL] Start MCP server: {e}')

# 3. Health check
try:
    r = urllib.request.urlopen(f'{base}/api/tools/mcp/servers/test-mcp/health', timeout=5)
    data = json.loads(r.read())
    print(f'[OK] Health check: status={data.get("status")}')
except Exception as e:
    print(f'[FAIL] Health check: {e}')

# 4. Get tools
try:
    r = urllib.request.urlopen(f'{base}/api/tools/mcp/servers/test-mcp/tools', timeout=5)
    data = json.loads(r.read())
    tool_count = len(data.get('tools', []))
    print(f'[OK] Get tools: {tool_count} tools')
except Exception as e:
    print(f'[FAIL] Get tools: {e}')

# 5. Call tool (echo)
try:
    payload = json.dumps({'server_name': 'test-mcp', 'tool_name': 'echo', 'arguments': {'text': 'hello from backend'}}).encode()
    req = urllib.request.Request(f'{base}/api/tools/mcp/call', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    r = urllib.request.urlopen(req, timeout=10)
    data = json.loads(r.read())
    inner = data.get('result', {})
    print(f'[OK] Call tool echo: status={data.get("status")}, inner_success={inner.get("success")}')
except Exception as e:
    print(f'[FAIL] Call tool echo: {e}')

# 6. Call tool (calculator)
try:
    payload = json.dumps({'server_name': 'test-mcp', 'tool_name': 'calculator', 'arguments': {'expression': '2 + 3 * 4'}}).encode()
    req = urllib.request.Request(f'{base}/api/tools/mcp/call', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    r = urllib.request.urlopen(req, timeout=10)
    data = json.loads(r.read())
    inner = data.get('result', {})
    inner_result = inner.get('result', {})
    print(f'[OK] Call tool calculator: status={data.get("status")}, inner_success={inner.get("success")}, result={inner_result.get("result")}')
except Exception as e:
    print(f'[FAIL] Call tool calculator: {e}')

# 7. Sync all tools
try:
    req = urllib.request.Request(f'{base}/api/tools/mcp/sync', method='POST')
    r = urllib.request.urlopen(req, timeout=10)
    data = json.loads(r.read())
    print(f'[OK] Sync all tools: count={data.get("count")}')
except Exception as e:
    print(f'[FAIL] Sync all tools: {e}')

# 8. List servers
try:
    r = urllib.request.urlopen(f'{base}/api/tools/mcp/servers', timeout=5)
    data = json.loads(r.read())
    stats = data.get('statistics', {})
    print(f'[OK] List servers: total={stats.get("total_servers")}, connected={stats.get("connected_servers")}')
except Exception as e:
    print(f'[FAIL] List servers: {e}')

# 9. Stop server
try:
    payload = json.dumps({'name': 'test-mcp'}).encode()
    req = urllib.request.Request(f'{base}/api/tools/mcp/servers/stop', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    r = urllib.request.urlopen(req, timeout=5)
    data = json.loads(r.read())
    print(f'[OK] Stop server: {data.get("status")}')
except Exception as e:
    print(f'[FAIL] Stop server: {e}')

# 10. Delete server
try:
    req = urllib.request.Request(f'{base}/api/tools/mcp/servers/test-mcp', method='DELETE')
    r = urllib.request.urlopen(req, timeout=5)
    data = json.loads(r.read())
    print(f'[OK] Delete server: {data.get("status")}')
except Exception as e:
    print(f'[FAIL] Delete server: {e}')

# Cleanup
mock.stop()
print()
print('Mock MCP server stopped. Test complete.')
