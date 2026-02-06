with open(r'd:\CXHMS\backend\core\memory\manager.py', 'r', encoding='utf-8') as f:
    content = f.read()
    
# Find all triple quote positions
import re
pattern = r"'''"
matches = list(re.finditer(pattern, content))

print(f'Total triple quotes found: {len(matches)}')
for i, match in enumerate(matches):
    start = match.start()
    line_num = content[:start].count('\n') + 1
    context_start = max(0, start - 20)
    context_end = min(len(content), start + 20)
    context = content[context_start:context_end].replace('\n', '\\n')
    print(f'{i+1}. Line {line_num}: ...{context}...')
