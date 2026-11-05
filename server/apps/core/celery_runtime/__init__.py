"""Celery 公共运行架构，不依赖业务应用初始化。"""

from contextvars import ContextVar

skip_periodic_sync = ContextVar("celery_runtime_skip_periodic_sync", default=False)


def inspect_registry(app):
    """管理命令即使通过 call_command 调用，也不能因注册任务而写周期表。"""
    token = skip_periodic_sync.set(True)
    try:
        app.loader.import_default_modules()
        return dict(app.tasks)
    finally:
        skip_periodic_sync.reset(token)
