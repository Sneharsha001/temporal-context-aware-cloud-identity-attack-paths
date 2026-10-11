import subprocess
import time
import json
import os
import sys
from datetime import datetime, timezone

def run_suite(name, repo_path, python_path, log_file):
    print(f"=== Starting Full Suite: {name} ===")
    print(f"CWD: {repo_path}")
    print(f"Python: {python_path}")
    print(f"Log target: {log_file}")
    
    start_dt = datetime.now(timezone.utc)
    t0 = time.time()
    
    cmd = [python_path, "-m", "pytest", "-q"]
    
    timed_out = False
    stdout = ""
    stderr = ""
    exit_code = None
    
    try:
        # Bounded timeout of 1200 seconds (20 minutes)
        proc = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=1200,
        )
        t1 = time.time()
        elapsed = t1 - t0
        exit_code = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired as e:
        t1 = time.time()
        elapsed = t1 - t0
        timed_out = True
        exit_code = -1
        stdout = e.stdout or ""
        stderr = (e.stderr or "") + "\nTIMEOUT: Execution exceeded 1200 seconds (20 minutes)."
    
    end_dt = datetime.now(timezone.utc)
    
    # Save raw log
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"COMMAND: {' '.join(cmd)}\n")
        f.write(f"CWD: {repo_path}\n")
        f.write(f"PYTHON: {python_path}\n")
        f.write(f"START_UTC: {start_dt.isoformat()}\n")
        f.write(f"END_UTC: {end_dt.isoformat()}\n")
        f.write(f"ELAPSED_SEC: {elapsed:.2f}\n")
        f.write(f"EXIT_CODE: {exit_code}\n")
        f.write(f"TIMED_OUT: {timed_out}\n\n")
        f.write("=== STDOUT ===\n")
        f.write(stdout)
        f.write("\n=== STDERR ===\n")
        f.write(stderr)
    
    print(f"Finished {name}: exit_code={exit_code}, elapsed={elapsed:.2f}s")
    
    return {
        "workspace": name,
        "repo_path": repo_path,
        "python_path": python_path,
        "command": cmd,
        "start_utc": start_dt.isoformat(),
        "end_utc": end_dt.isoformat(),
        "elapsed_sec": round(elapsed, 2),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "log_file": log_file,
        "stdout_tail": stdout[-2000:] if stdout else "",
        "stderr": stderr,
    }

if __name__ == "__main__":
    out_dir = r"C:\SNEHARSHA\ANTIGRAVITY\VERIFICATION-ARTIFACTS\ARF-RT-BASELINE-VERIFICATION"
    
    res_baseline = run_suite(
        "BASELINE",
        r"C:\SNEHARSHA\ANTIGRAVITY\Artifact\ARF-RT-BASELINE",
        r"C:\SNEHARSHA\ANTIGRAVITY\Artifact\ARF-RT-BASELINE\.venv\Scripts\python.exe",
        os.path.join(out_dir, "full_suite_baseline.log")
    )
    
    res_temporal = run_suite(
        "RESEARCH_TEMPORAL",
        r"C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL",
        r"C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL\.venv\Scripts\python.exe",
        os.path.join(out_dir, "full_suite_temporal.log")
    )
    
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "suites": {
            "BASELINE": res_baseline,
            "RESEARCH_TEMPORAL": res_temporal,
        }
    }
    
    summary_path = os.path.join(out_dir, "execution_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    
    print(f"Saved machine-readable execution summary to: {summary_path}")
