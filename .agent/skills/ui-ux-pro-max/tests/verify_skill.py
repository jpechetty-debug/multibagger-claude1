import subprocess
import json
import os
import sys

def run_command(cmd):
    try:
        # Use explicit encoding for Windows compatibility with Unicode chars
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True, encoding='utf-8')
        return result
    except Exception as e:
        print(f"Subprocess error: {e}")
        return None

def test_search_domain():
    print("Testing domain search (ux)...")
    cmd = 'python scripts/search.py "accessibility" --domain ux --json'
    res = run_command(cmd)
    if not res or res.returncode != 0:
        print(f"FAILED: {res.stderr if res else 'No result'}")
        return False
    try:
        data = json.loads(res.stdout)
        if not data.get("results"):
            print("FAILED: No results for accessibility")
            return False
    except json.JSONDecodeError:
        print(f"FAILED: Invalid JSON output: {res.stdout[:100]}...")
        return False
    print("PASSED")
    return True

def test_design_system():
    print("Testing design system generation...")
    cmd = 'python scripts/search.py "SaaS Dashboard" --design-system'
    res = run_command(cmd)
    if not res or res.returncode != 0:
        print(f"FAILED: {res.stderr if res else 'No result'}")
        return False
    if "TARGET: SAAS DASHBOARD" not in res.stdout.upper():
        print("FAILED: Design system header missing")
        return False
    print("PASSED")
    return True

def test_reasoning_engine():
    print("Testing reasoning engine (Fintech)...")
    cmd = 'python scripts/search.py "Fintech" --design-system'
    res = run_command(cmd)
    # The current match for "Fintech" is "Conversion-Optimized" (No. 6 Fintech/Crypto)
    if "CONVERSION-OPTIMIZED" not in res.stdout.upper() and "FINTECH" not in res.stdout.upper():
        print("FAILED: Reasoning engine did not match Fintech category")
        return False
    print("PASSED")
    return True

if __name__ == "__main__":
    # Change to skill directory to run tests
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    success = True
    success &= test_search_domain()
    success &= test_design_system()
    success &= test_reasoning_engine()
    
    if success:
        print("\nALL TESTS PASSED")
        sys.exit(0)
    else:
        print("\nSOME TESTS FAILED")
        sys.exit(1)
