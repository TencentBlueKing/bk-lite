"""公共 prefork 适配层保留 threads 的有效超时行为，不修改任务声明。"""

from unittest.mock import Mock

import pytest
from celery import Celery

from apps.core.celery_runtime.pool import ThreadCompatiblePreforkPool

pytestmark = pytest.mark.unit


def test_task_limits_are_not_forwarded_but_callbacks_and_arguments_are_preserved():
    app = Celery("pool_contract", fixups=[], set_as_current=False)
    pool = ThreadCompatiblePreforkPool(1, app=app, timeout=2, soft_timeout=1, maxtasksperchild=5, max_memory_per_child=64)
    delegate = Mock()
    pool.on_apply = delegate
    callback = Mock()
    pool.apply_async(str, args=[123], kwargs={}, timeout=2, soft_timeout=1, callback=callback)
    assert delegate.call_args.args == (str, [123], {})
    assert delegate.call_args.kwargs["callback"] is callback
    assert delegate.call_args.kwargs.get("timeout") is None
    assert delegate.call_args.kwargs.get("soft_timeout") is None
    assert all(pool.options[key] is None for key in ("timeout", "soft_timeout", "maxtasksperchild", "max_memory_per_child"))
    app.close()
