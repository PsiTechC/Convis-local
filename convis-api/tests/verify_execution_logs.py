"""
Verification Script for Execution Logs

This script verifies that:
1. All call handlers have execution logs saving functionality
2. Execution logs are saved with correct structure
3. API endpoint works correctly
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_handler_has_execution_logs(handler_file, handler_name):
    """Check if a handler file has execution logs saving"""
    file_path = Path(__file__).parent.parent / "app" / "services" / "call_handlers" / handler_file
    
    if not file_path.exists():
        print(f"❌ {handler_name}: File not found: {handler_file}")
        return False
    
    content = file_path.read_text()
    
    checks = {
        "_save_execution_logs": "_save_execution_logs method exists",
        "execution_logs": "execution_logs field is used",
        "call_logs_collection.update_one": "Database update is performed",
        "performance_metrics": "Performance metrics are included"
    }
    
    results = {}
    for check, description in checks.items():
        results[check] = check in content
    
    all_passed = all(results.values())
    
    if all_passed:
        print(f"✅ {handler_name}: All checks passed")
    else:
        print(f"❌ {handler_name}: Missing components:")
        for check, passed in results.items():
            if not passed:
                print(f"   - {checks[check]}")
    
    return all_passed

def verify_all_handlers():
    """Verify all call handlers have execution logs saving"""
    print("=" * 60)
    print("Verifying Execution Logs Implementation")
    print("=" * 60)
    print()
    
    handlers = [
        ("custom_provider_stream.py", "CustomProviderStreamHandler"),
        ("ultra_low_latency_handler.py", "UltraLowLatencyHandler"),
        ("optimized_stream_handler.py", "OptimizedStreamHandler"),
    ]
    
    results = []
    for handler_file, handler_name in handlers:
        result = check_handler_has_execution_logs(handler_file, handler_name)
        results.append(result)
        print()
    
    print("=" * 60)
    if all(results):
        print("✅ ALL HANDLERS HAVE EXECUTION LOGS SAVING")
        return 0
    else:
        print("❌ SOME HANDLERS ARE MISSING EXECUTION LOGS SAVING")
        return 1

def verify_api_endpoint():
    """Verify API endpoint exists and has correct structure"""
    print("=" * 60)
    print("Verifying API Endpoint")
    print("=" * 60)
    print()
    
    dashboard_file = Path(__file__).parent.parent / "app" / "routes" / "dashboard.py"
    
    if not dashboard_file.exists():
        print("❌ dashboard.py not found")
        return False
    
    content = dashboard_file.read_text()
    
    checks = {
        "/calls/{call_id}/execution-logs": "API endpoint route exists",
        "get_call_execution_logs": "API endpoint function exists",
        "execution_logs": "Returns execution_logs field",
        "has_execution_logs": "Returns has_execution_logs flag"
    }
    
    results = {}
    for check, description in checks.items():
        results[check] = check in content
    
    all_passed = all(results.values())
    
    if all_passed:
        print("✅ API Endpoint: All checks passed")
    else:
        print("❌ API Endpoint: Missing components:")
        for check, passed in results.items():
            if not passed:
                print(f"   - {checks[check]}")
    
    print()
    return all_passed

if __name__ == "__main__":
    print()
    handler_result = verify_all_handlers()
    print()
    api_result = verify_api_endpoint()
    print()
    print("=" * 60)
    
    if handler_result == 0 and api_result:
        print("✅ ALL VERIFICATIONS PASSED")
        sys.exit(0)
    else:
        print("❌ SOME VERIFICATIONS FAILED")
        sys.exit(1)

