
with open('Newmultibagger-main/worker/tasks.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

out = lines[:319]

new_task = '''
@app.task(name="worker.tasks.refresh_stale_data", bind=True,
          max_retries=2, default_retry_delay=60)
@celery_task_timer("refresh_stale_data")
def refresh_stale_data(self, symbol: str):
    try:
        from modules.data_layer.data_service import get_data_manager
        from modules.data_utils import run_coroutine_sync
        dm = get_data_manager()
        run_coroutine_sync(dm.async_fetch_fundamentals(symbol))
        logger.info("Stale data refreshed", symbol=symbol)
    except Exception as exc:
        logger.warning("refresh_stale_data failed", symbol=symbol, error=str(exc))
        raise self.retry(exc=exc)
'''
out.append(new_task)

with open('Newmultibagger-main/worker/tasks.py', 'w', encoding='utf-8') as f:
    f.writelines(out)
