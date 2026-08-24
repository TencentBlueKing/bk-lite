import asyncio
from unittest.mock import patch

from utils import async_executor as async_executor_module


def test_execute_tasks_emits_one_debug_summary_without_info():
    executor = async_executor_module.AsyncExecutor()

    async def task():
        return "done"

    with (
        patch.object(async_executor_module.logger, "info") as info,
        patch.object(async_executor_module.logger, "debug") as debug,
    ):
        result = asyncio.run(executor.execute_tasks([task]))

        assert result == ["done"]
        info.assert_not_called()
        debug.assert_called_once_with("event=async_tasks_completed task_count=%s", 1)
