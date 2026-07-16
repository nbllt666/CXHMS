"""检查 agent 列表和最近创建的 agent。"""
import urllib.request
import json

req = urllib.request.Request('http://localhost:8001/api/agents', method='GET')
r = urllib.request.urlopen(req, timeout=10)
data = json.loads(r.read())

agents = data if isinstance(data, list) else data.get('agents', data.get('data', []))
print(f'total agents: {len(agents)}')
for a in agents[-5:]:
    aid = a.get('id')
    name = a.get('name')
    desc = (a.get('description') or '')[:60]
    print(f'  - id={aid}, name={name}, desc={desc}')
