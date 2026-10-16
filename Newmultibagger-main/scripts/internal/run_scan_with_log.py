"""
Runner script to execute screener.py while streaming stdout/stderr simultaneously
to the terminal and a persistent log file in runtime/scan_<timestamp>.log.
"""
import os
import subprocess
import sys
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(PROJECT_ROOT)
os.environ["PYTHONIOENCODING"] = "utf-8"

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = os.path.join(PROJECT_ROOT, "runtime", f"scan_{timestamp}.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)

print(f"Starting scan with persistent log at: {log_path}", flush=True)

screener_script = os.path.join(PROJECT_ROOT, "scripts", "internal", "screener.py")
cmd = [sys.executable, "-u", screener_script] + sys.argv[1:]

with open(log_path, "w", encoding="utf-8", buffering=1) as f:
    f.write(f"=== Scan started at {datetime.now().isoformat()} ===\n")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    if proc.stdout:
        for line in proc.stdout:
            try:
                sys.stdout.write(line)
                sys.stdout.flush()
            except Exception:
                pass
            try:
                f.write(line)
                f.flush()
            except Exception:
                pass
    proc.wait()
    f.write(f"\n=== Scan finished with exit code {proc.returncode} at {datetime.now().isoformat()} ===\n")

sys.exit(proc.returncode)
