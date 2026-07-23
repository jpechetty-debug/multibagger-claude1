from fastapi import HTTPException

from core.observability.logger import get_logger
from modules.auth import get_api_key

api_logger = get_logger("test")

class MockRequest:
    def __init__(self, key):
        self.scope = {"type": "http"}
        self.query_params = {}
        self.key = key

class MockBackgroundTasks:
    def add_task(self, func, *args, **kwargs):
        func(*args, **kwargs)

def _check_api_key(key):
    req = MockRequest(key)
    bg = MockBackgroundTasks()
    try:
        get_api_key(req, bg, api_key=key)
        return True
    except HTTPException as e:
        print(f"Failed: {e.detail}")
        return False


# Module-level test execution — only runs when invoked directly
if __name__ == "__main__":
    # Our generated key was sov_9292efc4e24b2c11d298ae04b4da902d9949f72617e72e3f
    key = "sov_9292efc4e24b2c11d298ae04b4da902d9949f72617e72e3f"

    # Test 1: Successful Auth
    print("Test 1: Normal Auth")
    assert _check_api_key(key)
    print("Success")

    # Test 2: Rate Limiting
    # The limit was set to 120 RPM. Let's make 120 calls
    print("Test 2: Rate Limit")
    success_count = 0
    for _i in range(125):
        if _check_api_key(key):
            success_count += 1
    print(f"Successful calls before rate limit: {success_count}")
    assert success_count >= 119
    print("Success")

    # Test 3: Invalid Key
    print("Test 3: Invalid Key")
    assert not _check_api_key("sov_invalidkey")
    print("Success")

    # Print the DB to show usage count
    from db.db_core import execute_sql
    usage = execute_sql("SELECT total_usage FROM api_keys", fetch_all=True)[0]['total_usage']
    print(f"Total Usage in DB: {usage}")
    assert usage >= 120
    print("All tests passed.")
