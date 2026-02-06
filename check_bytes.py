with open(r'd:\CXHMS\backend\core\memory\manager.py', 'rb') as f:
    content = f.read()
    
# Find line 196
lines = content.split(b'\n')
print(f'Total lines: {len(lines)}')
print(f'Line 196 length: {len(lines[195])}')
print(f'Line 196 bytes: {lines[195]}')
print(f'Line 196 repr: {repr(lines[195])}')

# Check for quote characters
quote_chars = set()
for line in lines:
    for byte in line:
        if byte in [ord("'"), ord('"'), ord('`')]:
            quote_chars.add(byte)
print(f'Quote characters found: {quote_chars}')

# Check line 209
print(f'\nLine 209 length: {len(lines[208])}')
print(f'Line 209 bytes: {lines[208]}')
print(f'Line 209 repr: {repr(lines[208])}')
