#!/usr/bin/env python3
"""
Comprehensive Test Runner for Convis API
Runs all tests: unit, integration, performance, and functionality tests
"""
import sys
import subprocess
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def run_command(cmd, description):
    """Run a command and return success status"""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"{'='*60}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            print(f"✅ {description} - PASSED")
            if result.stdout:
                print(result.stdout)
            return True
        else:
            print(f"❌ {description} - FAILED")
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)
            return False
    except Exception as e:
        print(f"❌ {description} - ERROR: {str(e)}")
        return False

def check_health_endpoints():
    """Check if health endpoints are accessible"""
    import requests
    try:
        # Test main health endpoint
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            print("✅ Main health endpoint - OK")
            return True
        else:
            print(f"❌ Main health endpoint - Status: {response.status_code}")
            return False
    except Exception as e:
        print(f"⚠️  Health endpoint check skipped (server may not be running): {str(e)}")
        return None

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("CONVIS API - COMPREHENSIVE TEST SUITE")
    print("="*60)
    
    # Change to tests directory
    os.chdir(project_root)
    
    results = {
        "passed": 0,
        "failed": 0,
        "skipped": 0
    }
    
    # 1. Unit Tests
    print("\n📦 UNIT TESTS")
    tests = [
        ("python -m pytest tests/test_customer_data_extraction.py -v", "Customer Data Extraction Tests"),
        ("python -m pytest tests/test_voice_mode_indicators.py -v", "Voice Mode Indicator Tests"),
        ("python -m pytest tests/test_custom_provider_handler.py -v", "Custom Provider Handler Tests"),
    ]
    
    for cmd, desc in tests:
        if run_command(cmd, desc):
            results["passed"] += 1
        else:
            results["failed"] += 1
    
    # 2. Integration Tests (may require DB)
    print("\n🔗 INTEGRATION TESTS")
    integration_tests = [
        ("python -m pytest tests/test_assistant_api_integration.py -v -m integration", "Assistant API Integration Tests"),
        ("python -m pytest tests/test_call_logs_integration.py -v -m integration", "Call Logs Integration Tests"),
    ]
    
    for cmd, desc in integration_tests:
        if run_command(cmd, desc):
            results["passed"] += 1
        else:
            results["failed"] += 1
            results["skipped"] += 1  # Integration tests may fail if DB not available
    
    # 3. Code Quality Checks
    print("\n🔍 CODE QUALITY CHECKS")
    quality_checks = [
        ("python -m pytest tests/ --collect-only -q", "Test Discovery"),
    ]
    
    for cmd, desc in quality_checks:
        result = run_command(cmd, desc)
        if result is not None:
            if result:
                results["passed"] += 1
            else:
                results["failed"] += 1
    
    # 4. Health Endpoint Check
    print("\n🏥 HEALTH CHECKS")
    health_result = check_health_endpoints()
    if health_result is True:
        results["passed"] += 1
    elif health_result is None:
        results["skipped"] += 1
    else:
        results["failed"] += 1
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"✅ Passed: {results['passed']}")
    print(f"❌ Failed: {results['failed']}")
    print(f"⚠️  Skipped: {results['skipped']}")
    print("="*60)
    
    if results['failed'] == 0:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {results['failed']} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())

