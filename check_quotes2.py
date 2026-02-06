with open(r'd:\CXHMS\backend\core\memory\manager.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    in_triple = False
    start_line = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("'''") and not in_triple:
            in_triple = True
            start_line = i
            print(f'Opening triple quote at line {i}: {repr(stripped[:30])}')
        elif stripped.endswith("''')") and in_triple:
            in_triple = False
            print(f'Closing triple quote at line {i}: {repr(stripped[:30])}')
        elif stripped.endswith("''',") and in_triple:
            in_triple = False
            print(f'Closing triple quote at line {i}: {repr(stripped[:30])}')
        elif stripped.endswith("'''") and in_triple and not stripped.endswith("''')") and not stripped.endswith("''',"):
            in_triple = False
            print(f'Closing triple quote at line {i}: {repr(stripped[:30])}')
    
    if in_triple:
        print(f'WARNING: Unclosed triple quote starting at line {start_line}')
