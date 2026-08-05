import asyncio


async def cancel_tasks_created_after(existing_tasks):
    current = asyncio.current_task()
    pending = [task for task in asyncio.all_tasks() if task is not current and task not in existing_tasks and not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
