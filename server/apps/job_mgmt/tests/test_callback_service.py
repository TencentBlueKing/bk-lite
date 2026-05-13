"""回调服务单元测试"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import Retry


@pytest.mark.unit
class TestSendCallback:
    """测试 send_callback 入口函数"""

    def test_no_callback_url_does_nothing(self):
        from apps.job_mgmt.services.callback_service import send_callback

        execution = MagicMock()
        execution.callback_url = None

        with patch("apps.job_mgmt.services.callback_service.current_app") as mock_app:
            send_callback(execution)
            mock_app.send_task.assert_not_called()

    def test_empty_callback_url_does_nothing(self):
        from apps.job_mgmt.services.callback_service import send_callback

        execution = MagicMock()
        execution.callback_url = ""

        with patch("apps.job_mgmt.services.callback_service.current_app") as mock_app:
            send_callback(execution)
            mock_app.send_task.assert_not_called()

    def test_sends_celery_task_when_url_present(self):
        from apps.job_mgmt.services.callback_service import send_callback

        execution = MagicMock()
        execution.callback_url = "http://example.com/callback"
        execution.id = 1
        execution.status = "success"
        execution.total_count = 3
        execution.success_count = 3
        execution.failed_count = 0
        execution.finished_at = datetime(2026, 4, 30, 10, 0, 0)

        with patch("apps.job_mgmt.services.callback_service.current_app") as mock_app:
            send_callback(execution)
            mock_app.send_task.assert_called_once_with(
                "apps.job_mgmt.tasks.do_callback_task",
                args=[
                    "http://example.com/callback",
                    {
                        "task_id": 1,
                        "status": "success",
                        "total_count": 3,
                        "success_count": 3,
                        "failed_count": 0,
                        "finished_at": "2026-04-30T10:00:00",
                    },
                    1,
                ],
            )


@pytest.mark.unit
class TestDoCallbackTask:
    """测试 do_callback_task Celery 任务的核心逻辑

    autoretry_for=(Exception,) 意味着所有异常都会被 Celery 捕获并触发 retry，
    retry 会抛出 celery.exceptions.Retry。因此错误场景需要 expect Retry。
    """

    def test_success_200(self):
        from apps.job_mgmt.tasks import do_callback_task

        with patch("apps.job_mgmt.tasks.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            do_callback_task("http://example.com/cb", {"task_id": 1}, 1)
            mock_post.assert_called_once_with("http://example.com/cb", json={"task_id": 1}, timeout=10)

    def test_success_201(self):
        from apps.job_mgmt.tasks import do_callback_task

        with patch("apps.job_mgmt.tasks.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=201)
            do_callback_task("http://example.com/cb", {"task_id": 1}, 1)
            mock_post.assert_called_once()

    def test_raises_on_non_2xx(self):
        from apps.job_mgmt.tasks import do_callback_task

        with patch("apps.job_mgmt.tasks.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=500)
            with pytest.raises((RuntimeError, Retry)):
                do_callback_task("http://example.com/cb", {"task_id": 1}, 1)

    def test_raises_on_400(self):
        from apps.job_mgmt.tasks import do_callback_task

        with patch("apps.job_mgmt.tasks.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=400)
            with pytest.raises((RuntimeError, Retry)):
                do_callback_task("http://example.com/cb", {"task_id": 1}, 1)

    def test_raises_on_network_error(self):
        import requests as req

        from apps.job_mgmt.tasks import do_callback_task

        with patch("apps.job_mgmt.tasks.requests.post") as mock_post:
            mock_post.side_effect = req.ConnectionError("connection refused")
            with pytest.raises((req.ConnectionError, Retry)):
                do_callback_task("http://example.com/cb", {"task_id": 1}, 1)
