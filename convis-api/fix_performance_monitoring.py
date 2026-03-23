#!/usr/bin/env python3
"""
Script to wrap performance monitoring calls with conditional checks
This prevents overhead when performance monitoring is disabled
"""

import re
import sys

def fix_performance_monitoring_calls(file_path):
    """Add conditional checks around performance monitoring calls"""

    with open(file_path, 'r') as f:
        content = f.read()

    lines = content.split('\n')
    fixed_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Check if this line has a performance monitoring call that needs wrapping
        if 'self.perf_monitor.' in line and 'if self.perf_monitor' not in line and 'return self.perf_monitor' not in line:
            indent = len(line) - len(line.lstrip())

            # Special handling for 'with' statements
            if 'with self.perf_monitor.track' in line:
                # Already wrapped by helper method, use it instead
                fixed_lines.append(line.replace('self.perf_monitor.track', 'self._track_performance'))
            elif '.start_turn()' in line or '.end_turn()' in line or '.log_session_summary()' in line:
                # Wrap single-line calls
                fixed_lines.append(' ' * indent + 'if self.perf_monitor:')
                fixed_lines.append(' ' * (indent + 4) + line.strip())
            else:
                fixed_lines.append(line)

        elif 'self.call_logger.' in line and 'if self.call_logger' not in line and 'method = getattr(self.call_logger' not in line:
            # Wrap call_logger calls
            indent = len(line) - len(line.lstrip())

            # Check if it's a multi-line call
            if '(' in line and ')' not in line:
                # Multi-line call
                fixed_lines.append(' ' * indent + 'if self.call_logger:')
                fixed_lines.append(' ' * (indent + 4) + line.strip())

                # Continue adding lines until we find the closing paren
                i += 1
                while i < len(lines) and ')' not in lines[i]:
                    fixed_lines.append(' ' * (indent + 4) + lines[i].strip())
                    i += 1
                if i < len(lines):
                    fixed_lines.append(' ' * (indent + 4) + lines[i].strip())
            else:
                # Single line call
                fixed_lines.append(' ' * indent + 'if self.call_logger:')
                fixed_lines.append(' ' * (indent + 4) + line.strip())
        else:
            fixed_lines.append(line)

        i += 1

    # Write fixed content
    with open(file_path, 'w') as f:
        f.write('\n'.join(fixed_lines))

    print(f"✅ Fixed performance monitoring calls in {file_path}")

if __name__ == '__main__':
    file_path = 'app/services/call_handlers/custom_provider_stream.py'
    fix_performance_monitoring_calls(file_path)
    print("Done!")
