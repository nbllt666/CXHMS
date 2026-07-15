"""CXFC 端到端验证脚本"""
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

# Setup paths
_PROJECT_ROOT = os.getcwd()
_TESTS_TOOLS = os.path.join(_PROJECT_ROOT, 'tests', 'test_tools')
sys.path.insert(0, _TESTS_TOOLS)
sys.path.insert(0, _PROJECT_ROOT)

from cxfc.mock_plugin_server import MockPluginServer
from cxfc.preset_tools import get_preset_definitions, get_preset_skills, list_tool_names

# Start mock plugin server
mock = MockPluginServer(
    host='127.0.0.1',
    port=9000,
    name='E2E测试插件',
    tools=get_preset_definitions(),
    capabilities=['tools', 'skills', 'events'],
    skills=get_preset_skills(),
    main_system_url=base,
    heartbeat_interval=10.0,
)
mock.start()
print(f'Mock plugin server started on port 9000')
time.sleep(1)

# Verify mock plugin server endpoints
print()
print('=== Mock Plugin Server Direct Tests ===')

try:
    r = urllib.request.urlopen('http://127.0.0.1:9000/health', timeout=3)
    print(f'[OK] Mock /health: {json.loads(r.read())}')
except Exception as e:
    print(f'[FAIL] Mock /health: {e}')

try:
    r = urllib.request.urlopen('http://127.0.0.1:9000/tools', timeout=3)
    tools = json.loads(r.read())
    print(f'[OK] Mock /tools: {len(tools.get("tools", []))} tools')
except Exception as e:
    print(f'[FAIL] Mock /tools: {e}')

try:
    r = urllib.request.urlopen('http://127.0.0.1:9000/skills', timeout=3)
    skills = json.loads(r.read())
    print(f'[OK] Mock /skills: {len(skills.get("skills", []))} skills')
except Exception as e:
    print(f'[FAIL] Mock /skills: {e}')

try:
    req = urllib.request.Request('http://127.0.0.1:9000/call',
        data=json.dumps({'tool': 'echo', 'arguments': {'text': 'cxfc-test'}}).encode(),
        headers={'Content-Type': 'application/json'})
    r = urllib.request.urlopen(req, timeout=3)
    print(f'[OK] Mock /call echo: {json.loads(r.read())}')
except Exception as e:
    print(f'[FAIL] Mock /call echo: {e}')

# Register plugin to main system
print()
print('=== CXFC Backend API Tests ===')

plugin_id = None

# 1. Register plugin
try:
    payload = json.dumps({
        'host': '127.0.0.1',
        'port': 9000,
        'name': 'E2E测试插件',
        'tools': get_preset_definitions(),
        'capabilities': ['tools', 'skills', 'events'],
        'skills': get_preset_skills(),
    }).encode()
    req = urllib.request.Request(f'{base}/api/cxfc/register', data=payload,
                                 headers={'Content-Type': 'application/json'}, method='POST')
    r = urllib.request.urlopen(req, timeout=5)
    data = json.loads(r.read())
    plugin_id = data.get('plugin_id')
    print(f'[OK] Register plugin: plugin_id={plugin_id}')
except Exception as e:
    print(f'[FAIL] Register plugin: {e}')

# 2. Discover plugins
try:
    r = urllib.request.urlopen(f'{base}/api/cxfc/discover', timeout=5)
    data = json.loads(r.read())
    plugins = data.get('plugins', [])
    print(f'[OK] Discover plugins: {len(plugins)} plugins found')
    for p in plugins:
        print(f'     - {p.get("plugin_id", "?")}: {p.get("name", "?")} (status={p.get("status", "?")})')
except Exception as e:
    print(f'[FAIL] Discover plugins: {e}')

# 3. Get skills
try:
    r = urllib.request.urlopen(f'{base}/api/cxfc/skills', timeout=5)
    data = json.loads(r.read())
    skills = data.get('skills', [])
    if isinstance(skills, dict):
        skill_count = len(skills)
    else:
        skill_count = len(skills)
    print(f'[OK] Get skills: {skill_count} skills')
except Exception as e:
    print(f'[FAIL] Get skills: {e}')

# 4. List plugins
try:
    r = urllib.request.urlopen(f'{base}/api/cxfc/plugins', timeout=5)
    data = json.loads(r.read())
    plugins = data.get('plugins', [])
    if isinstance(plugins, dict):
        plugin_count = len(plugins)
    else:
        plugin_count = len(plugins)
    print(f'[OK] List plugins: {plugin_count} plugins')
except Exception as e:
    print(f'[FAIL] List plugins: {e}')

# 5. Heartbeat
if plugin_id:
    try:
        payload = json.dumps({'plugin_id': plugin_id, 'port': 9000}).encode()
        req = urllib.request.Request(f'{base}/api/cxfc/heartbeat', data=payload,
                                     headers={'Content-Type': 'application/json'}, method='POST')
        r = urllib.request.urlopen(req, timeout=5)
        data = json.loads(r.read())
        print(f'[OK] Heartbeat: status={data.get("status")}')
    except Exception as e:
        print(f'[FAIL] Heartbeat: {e}')

# 6. Call tool via main system
if plugin_id:
    try:
        payload = json.dumps({'tool': 'echo', 'arguments': {'text': 'hello via backend'}}).encode()
        req = urllib.request.Request(f'{base}/api/cxfc/plugins/{plugin_id}/call', data=payload,
                                     headers={'Content-Type': 'application/json'}, method='POST')
        r = urllib.request.urlopen(req, timeout=10)
        data = json.loads(r.read())
        print(f'[OK] Call tool echo: {json.dumps(data, ensure_ascii=False)[:200]}')
    except Exception as e:
        print(f'[FAIL] Call tool echo: {e}')

# 7. Call calculator via main system
if plugin_id:
    try:
        payload = json.dumps({'tool': 'calculator', 'arguments': {'expression': '10 + 20'}}).encode()
        req = urllib.request.Request(f'{base}/api/cxfc/plugins/{plugin_id}/call', data=payload,
                                     headers={'Content-Type': 'application/json'}, method='POST')
        r = urllib.request.urlopen(req, timeout=10)
        data = json.loads(r.read())
        print(f'[OK] Call tool calculator: {json.dumps(data, ensure_ascii=False)[:200]}')
    except Exception as e:
        print(f'[FAIL] Call tool calculator: {e}')

# 8. Delete plugin
if plugin_id:
    try:
        req = urllib.request.Request(f'{base}/api/cxfc/plugins/{plugin_id}', method='DELETE')
        r = urllib.request.urlopen(req, timeout=5)
        data = json.loads(r.read())
        print(f'[OK] Delete plugin: {json.dumps(data, ensure_ascii=False)[:200]}')
    except Exception as e:
        print(f'[FAIL] Delete plugin: {e}')

# Cleanup
mock.stop()
print()
print('Mock plugin server stopped. CXFC test complete.')
