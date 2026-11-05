with open(r"C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL\tests\research\test_rdce_property_based.py", "rb") as f:
    data = f.read()

lines = data.split(b"\n")
for i, line in enumerate(data.split(b"\n")[128:145], 129):
    try:
        line.decode("utf-8")
    except UnicodeDecodeError as e:
        print(f"Line {i}: DECODE ERROR: {e}")
    
    for j, b in enumerate(line):
        if b == 0x00 or (b > 127 and b not in (0x0a, 0x0d, 0x09, 0x20)):
            ch = chr(b) if 32 <= b < 127 else "?"
            print(f"  Odd byte at pos {j}: 0x{b:02x} ({ch})")
    
    print(f"Line {i}: {line!r}")