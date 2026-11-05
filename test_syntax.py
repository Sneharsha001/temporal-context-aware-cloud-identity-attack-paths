import ast

with open(r"C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL\tests\research\test_rdce_property_based.py", "r", encoding="utf-8") as f:
    text = f.read()

try:
    ast.parse(text)
    print("Syntax OK")
except SyntaxError as e:
    print(f"SyntaxError at line {e.lineno}: {e.msg}")
    lines = text.split('\n')
    for i in range(max(0, e.lineno-3), min(len(text.split('\n')), e.lineno+2)):
        print(f"{i+1}: {repr(lines[i])}")