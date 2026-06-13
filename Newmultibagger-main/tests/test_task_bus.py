import asyncio
import pytest
from unittest.mock import patch, MagicMock

from worker.task_bus import dispatch, run_dev_worker, get_mode

@pytest.fixture(autouse=True)
def reset_task_bus_queue():
    import worker.task_bus
    worker.task_bus._queue = None
    yield

# A dummy task for testing
async def dummy_async_task(x, y):
    return x + y

def dummy_sync_task(x, y):
    return x * y

# Assign names to match CELERY task names if needed
dummy_async_task.name = "dummy_async_task"  # type: ignore
dummy_sync_task.name = "dummy_sync_task"  # type: ignore

@pytest.mark.asyncio
async def test_dispatch_asyncio_mode():
    """Test dispatch in asyncio mode (no celery broker)."""
    # Mock _MODE just in case test environment sets CELERY_BROKER_URL
    with patch("worker.task_bus._MODE", "asyncio"):
        assert get_mode() == "asyncio"

        # Test async task
        task_id = await dispatch(dummy_async_task, 1, 2)
        assert task_id.startswith("async-")

        # Run dev worker for exactly 1 task
        # To avoid blocking forever, we use run_dev_worker(max_tasks=1)
        await asyncio.wait_for(run_dev_worker(max_tasks=1), timeout=2.0)

        # Test sync task
        task_id = await dispatch(dummy_sync_task, 3, 4)
        assert task_id.startswith("async-")

        # Run dev worker for exactly 1 task
        await asyncio.wait_for(run_dev_worker(max_tasks=1), timeout=2.0)


@pytest.mark.asyncio
async def test_dispatch_celery_mode():
    """Test dispatch in celery mode."""
    with patch("worker.task_bus._MODE", "celery"):
        assert get_mode() == "celery"

        # We need to mock _dispatch_celery or app.send_task
        mock_result = MagicMock()
        mock_result.id = "mock-celery-id"

        with patch("worker.task_bus._dispatch_celery", return_value=mock_result.id) as mock_celery:
            task_id = await dispatch(dummy_async_task, 10, 20)

            assert task_id == "mock-celery-id"
            mock_celery.assert_called_once_with(dummy_async_task, 10, 20)
