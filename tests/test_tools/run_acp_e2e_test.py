"""ACP 端到端验证脚本"""
import urllib.request
import json
import time
import sys
import os
import uuid

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

from acp.acp_node import ACPNode

# External agent info
EXT_AGENT_ID = f'acp-e2e-test-{uuid.uuid4().hex[:8]}'
EXT_AGENT_NAME = 'E2E测试Agent'
EXT_HTTP_PORT = 8506  # Use a different port to avoid conflicts

# Start ACP node (external agent)
print()
print('=== Starting ACP Node (External Agent) ===')
node = ACPNode(
    agent_id=EXT_AGENT_ID,
    agent_name=EXT_AGENT_NAME,
    http_host='0.0.0.0',
    http_port=EXT_HTTP_PORT,
    capabilities=['chat', 'tools'],
)
result = node.start()
print(f'ACP node start: {result}')
time.sleep(1)

# Get main system agent info
print()
print('=== ACP Backend Tests ===')

main_agent_id = None
main_agent_name = None

# 1. Get main system health
try:
    r = urllib.request.urlopen(f'{base}/acp/health', timeout=5)
    data = json.loads(r.read())
    main_agent_id = data.get('agent_id')
    main_agent_name = data.get('agent_name')
    print(f'[OK] ACP health: agent_id={main_agent_id}, agent_name={main_agent_name}')
except Exception as e:
    print(f'[FAIL] ACP health: {e}')

# 2. Get main system info
try:
    r = urllib.request.urlopen(f'{base}/acp/info', timeout=5)
    data = json.loads(r.read())
    print(f'[OK] ACP info: {json.dumps(data, ensure_ascii=False)[:200]}')
except Exception as e:
    print(f'[FAIL] ACP info: {e}')

# 3. Get ACP stats
try:
    r = urllib.request.urlopen(f'{base}/api/acp/stats', timeout=5)
    data = json.loads(r.read())
    stats = data.get('statistics', {})
    print(f'[OK] ACP stats: local_agent={stats.get("local_agent_id", "?")}, agents={stats.get("total_agents", 0)}, messages={stats.get("total_messages", 0)}')
except Exception as e:
    print(f'[FAIL] ACP stats: {e}')

# 4. Register main system in ACP node
if main_agent_id:
    result = node.register_main_system(
        main_system_host='127.0.0.1',
        main_system_port=8001,
        main_system_agent_id=main_agent_id,
        main_system_agent_name=main_agent_name or 'Main System',
    )
    print(f'[OK] Register main system: {result.get("success")}')

# 5. Send message to main system via /acp/message
print()
print('=== Message Delivery Tests ===')

msg_id = str(uuid.uuid4())
test_message = {
    'id': msg_id,
    'msg_type': 'chat',
    'from_agent_id': EXT_AGENT_ID,
    'from_agent_name': EXT_AGENT_NAME,
    'to_agent_id': main_agent_id or '',
    'content': {'text': '你好，这是E2E测试消息！'},
    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    'metadata': {
        'from_host': '127.0.0.1',
        'from_port': EXT_HTTP_PORT,
    },
}

try:
    payload = json.dumps(test_message).encode()
    req = urllib.request.Request(f'{base}/acp/message', data=payload,
                                 headers={'Content-Type': 'application/json'}, method='POST')
    r = urllib.request.urlopen(req, timeout=10)
    data = json.loads(r.read())
    print(f'[OK] Send message to main: status={data.get("status")}, message_id={data.get("message_id")}')
except Exception as e:
    print(f'[FAIL] Send message to main: {e}')

# 6. Verify message appears in backend messages
time.sleep(1)
try:
    r = urllib.request.urlopen(f'{base}/api/acp/messages?agent_id={EXT_AGENT_ID}', timeout=5)
    data = json.loads(r.read())
    messages = data.get('messages', [])
    print(f'[OK] Get messages: {len(messages)} messages with {EXT_AGENT_ID}')
    for m in messages[-3:]:
        direction = 'sent' if m.get('is_sent') else 'received'
        content = m.get('content', {})
        text = content.get('text', str(content))[:80] if isinstance(content, dict) else str(content)[:80]
        print(f'     [{direction}] {m.get("from_agent_name", "?")} -> {m.get("to_agent_name", "?")}: {text}')
except Exception as e:
    print(f'[FAIL] Get messages: {e}')

# 7. Send message via ACP node's send_to_main_system
print()
print('=== ACP Node Message Tests ===')

result = node.send_to_main_system(
    main_system_host='127.0.0.1',
    main_system_port=8001,
    main_system_agent_id=main_agent_id or '',
    content={'text': '通过ACP节点发送的消息'},
    msg_type='chat',
)
print(f'[OK] Node send to main: success={result.get("success")}, error={result.get("error", "")}')

# 8. Wait for auto-reply (LLM may not be available — poll instead of fixed sleep)
print()
print('=== Auto-Reply Test (requires LLM) ===')
print('Polling for auto-reply (up to 30s, LLM may be slow or unavailable)...')

received = []
sent = []
poll_ok = False
for attempt in range(6):  # 6 attempts x 5s = 30s max
    if attempt > 0:
        time.sleep(5)
    try:
        r = urllib.request.urlopen(
            f'{base}/api/acp/messages?agent_id={EXT_AGENT_ID}', timeout=30
        )
        data = json.loads(r.read())
        messages = data.get('messages', [])
        received = [m for m in messages if not m.get('is_sent')]
        sent = [m for m in messages if m.get('is_sent')]
        poll_ok = True
        if received:
            break  # got a reply, no need to keep polling
    except Exception as e:
        print(f'     poll {attempt+1}/6 failed: {e}')

if poll_ok:
    print(f'[INFO] Messages: {len(sent)} sent, {len(received)} received')
    if received:
        print(f'[OK] Auto-reply received!')
        for m in received[-2:]:
            content = m.get('content', {})
            text = content.get('text', str(content))[:80] if isinstance(content, dict) else str(content)[:80]
            print(f'     Reply from {m.get("from_agent_name", "?")}: {text}')
    else:
        print(f'[WARN] No auto-reply (LLM may be unavailable or returned empty)')
else:
    print(f'[FAIL] Check auto-reply: all polls failed')

# 9. List known agents from node
print()
print('=== ACP Node Agent Discovery ===')
known_agents = node.list_known_agents()
print(f'[OK] Known agents: {len(known_agents)}')
for a in known_agents:
    print(f'     - {a.get("id", "?")}: {a.get("name", "?")} (host={a.get("host", "?")}:{a.get("port", "?")})')

# 10. Node statistics
stats = node.get_statistics()
print(f'[OK] Node stats: messages={stats.get("total_messages", 0)}, sent={stats.get("messages_sent", 0)}, received={stats.get("messages_received", 0)}')

# 11. Same-instance test: send message to self via /api/acp/send
print()
print('=== Same-Instance Self-Send Test ===')
if main_agent_id:
    try:
        payload = json.dumps({
            'to_agent_id': main_agent_id,
            'content': {'text': '自环测试消息'},
            'msg_type': 'chat',
        }).encode()
        req = urllib.request.Request(f'{base}/api/acp/send', data=payload,
                                     headers={'Content-Type': 'application/json'}, method='POST')
        r = urllib.request.urlopen(req, timeout=30)
        data = json.loads(r.read())
        print(f'[OK] Self-send: {json.dumps(data, ensure_ascii=False)[:200]}')
    except Exception as e:
        print(f'[FAIL] Self-send: {e}')

# Cleanup
node.stop()
print()
print('ACP node stopped. ACP test complete.')
