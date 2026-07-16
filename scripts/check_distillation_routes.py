import urllib.request, json

r = urllib.request.urlopen('http://localhost:8001/openapi.json', timeout=5)
d = json.loads(r.read().decode())
paths = [p for p in d.get('paths', {}).keys() if 'distillation' in p]
print('Distillation routes:')
for p in paths:
    methods = list(d['paths'][p].keys())
    print(f'  {p}: {methods}')
