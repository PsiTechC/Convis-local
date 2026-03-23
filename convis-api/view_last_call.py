"""
Quick script to view the last call's pipeline debug log.
Run: python view_last_call.py
"""
import os
import glob

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs", "pipeline")

if not os.path.exists(LOG_DIR):
    print(f"No pipeline logs found at {LOG_DIR}")
    exit(1)

# Get latest log file
log_files = sorted(glob.glob(os.path.join(LOG_DIR, "call_*.log")), reverse=True)

if not log_files:
    print("No pipeline log files found.")
    print(f"Logs directory: {LOG_DIR}")
    exit(1)

latest = log_files[0]
print(f"Latest log: {latest}\n")

with open(latest, "r") as f:
    print(f.read())
