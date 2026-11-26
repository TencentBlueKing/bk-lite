import pytest


@pytest.fixture
def delivery_worker(monkeypatch):
    """无需消息代理即可验证 worker 接收已提交的投递和清理任务。"""
    from apps.itsm.tasks import knowledge_attachment_cleanup, trigger_notice_tick

    for task in (trigger_notice_tick, knowledge_attachment_cleanup):

        def run(args, retry, current=task):
            return current.run(*args)

        monkeypatch.setattr(task, "apply_async", run)
