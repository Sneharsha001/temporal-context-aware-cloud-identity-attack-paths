with open('test_import.py', 'w') as f:
    f.write('import sys\n')
    f.write('sys.path.insert(0, "C:/SNEHARSHA/ANTIGRAVITY/ARF-RT-TEMPORAL")\n')
    f.write('import research\n')
    f.write('print("research:", research)\n')
    f.write('import research.ccpf\n')
    f.write('print("research.ccpf:", research.ccpf)\n')
    f.write('import research.ccpf.rdce\n')
    f.write('print("OK")\n')