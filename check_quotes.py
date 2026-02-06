import re

with open(r'd:\CXHMS\backend\core\memory\manager.py', 'r', encoding='utf-8') as f:
    content = f.read()
    open_triple = content.count("'''")
    close_triple = content.count("''',")
    print('Opening triple quotes:', open_triple)
    print('Closing triple quotes:', close_triple)
    print('Difference:', open_triple - close_triple)
