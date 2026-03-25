"""
Quick script to view the last call's pipeline debug log.
Run: python view_last_call.py
"""
import os

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs", "pipeline")

if not os.path.exists(LOG_DIR):
    print(f"No pipeline logs found at {LOG_DIR}")
    exit(1)

# Get all log files sorted by modification time (newest first)
log_files = [os.path.join(LOG_DIR, f) for f in os.listdir(LOG_DIR) if f.startswith("call_") and f.endswith(".log")]
log_files.sort(key=os.path.getmtime, reverse=True)

if not log_files:
    print("No pipeline log files found.")
    print(f"Logs directory: {LOG_DIR}")
    exit(1)

latest = log_files[0]
print(f"Latest log: {latest}")
print(f"Total logs: {len(log_files)}")
print()

with open(latest, "r") as f:
    print(f.read())
