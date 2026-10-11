import subprocess
import os
import sys

venvs = {
    'BASELINE': r'C:\SNEHARSHA\ANTIGRAVITY\Artifact\ARF-RT-BASELINE\.venv\Scripts\python.exe',
    'RESEARCH_TEMPORAL': r'C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL\.venv\Scripts\python.exe',
}

repos = {
    'BASELINE': r'C:\SNEHARSHA\ANTIGRAVITY\Artifact\ARF-RT-BASELINE',
    'RESEARCH_TEMPORAL': r'C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL',
}

out_lines = []

for name in ['BASELINE', 'RESEARCH_TEMPORAL']:
    py = venvs[name]
    repo = repos[name]
    out_lines.append(f'==================================================\nENVIRONMENT: {name}\nREPO: {repo}\nPYTHON: {py}\n==================================================\n')
    
    out_lines.append(f'Python exists: {os.path.exists(py)}\n')
    
    res = subprocess.run([py, '--version'], capture_output=True, text=True)
    out_lines.append(f'Python version: {res.stdout.strip()} {res.stderr.strip()}\n')
    
    res = subprocess.run([py, '-m', 'pip', 'list'], capture_output=True, text=True)
    out_lines.append(f'pip list:\n{res.stdout.strip()}\n')
    
    script = 'import arf_rt, pytest, pydantic, sys; print("arf_rt file:", arf_rt.__file__); print("pytest ver:", pytest.__version__); print("pydantic ver:", pydantic.__version__); print("sys.path:", sys.path[:5])'
    res = subprocess.run([py, '-c', script], cwd=repo, capture_output=True, text=True)
    out_lines.append(f'Import verification (cwd={repo}):\nstdout:\n{res.stdout.strip()}\nstderr:\n{res.stderr.strip()}\n')
    
    pyproject_path = os.path.join(repo, 'pyproject.toml')
    if os.path.exists(pyproject_path):
        with open(pyproject_path, 'r', encoding='utf-8') as f:
            out_lines.append(f'pyproject.toml:\n{f.read()}\n')

out_file = r'C:\SNEHARSHA\ANTIGRAVITY\VERIFICATION-ARTIFACTS\ARF-RT-BASELINE-VERIFICATION\stage_b_env_and_deps.txt'
with open(out_file, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out_lines))
print('Stage B environment and dependencies recorded to:', out_file)
