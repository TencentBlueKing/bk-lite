"""上游 prefork 的有效超时与回收契约不得被架构隔离取消。"""

from unittest.mock import Mock

import pytest
from celery import Celery
from celery.concurrency.prefork import TaskPool

pytestmark = pytest.mark.unit


def test_task_limits_recycling_callbacks_and_arguments_are_preserved():
    app = Celery("pool_contract", fixups=[], set_as_current=False)
    pool = TaskPool(1, app=app, timeout=2, soft_timeout=1, maxtasksperchild=5, max_memory_per_child=64)
    delegate = Mock()
    pool.on_apply = delegate
    callback = Mock()
    pool.apply_async(str, args=[123], kwargs={}, timeout=2, soft_timeout=1, callback=callback)
    assert delegate.call_args.args == (str, [123], {})
    assert delegate.call_args.kwargs["callback"] is callback
    assert delegate.call_args.kwargs["timeout"] == 2
    assert delegate.call_args.kwargs["soft_timeout"] == 1
    assert pool.options["maxtasksperchild"] == 5
    assert pool.options["max_memory_per_child"] == 64
    app.close()
