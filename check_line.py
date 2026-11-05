with open(r"C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL\tests\research\test_rdce_property_based.py", "rb") as f:
    data = f.read()

lines = data.split(b"\n")
line = lines[152]
print("Line 153:", repr(line))
print("Length:", len(line))
print("Ends with b')':", line.rstrip().endswith(b')'))
print("Ends with b') ->':", line.rstrip().endswith(b') ->'))
print("Last 20 bytes:", line[-20:] if len(line) >= 20 else line)