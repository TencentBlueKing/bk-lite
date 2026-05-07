"""回调服务单元测试"""

from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest


@pytest.mark.unit
class TestCallbackService:
    def test_no_callback_url_does_nothing(self):
        from apps.job_mgmt.services.callback_service import send_callback

        execution = MagicMock()
        execution.callback_url = None

        with patch("apps.job_mgmt.services.callback_service.threading") as mock_threading:
            send_callback(execution)
            mock_threading.Thread.assert_not_called()

    def test_empty_callback_url_does_nothing(self):
        from apps.job_mgmt.services.callback_service import send_callback

        execution = MagicMock()
        execution.callback_url = ""

        with patch("apps.job_mgmt.services.callback_service.threading") as mock_threading:
            send_callback(execution)
            mock_threading.Thread.assert_not_called()

    def test_starts_thread_when_url_present(self):
        from apps.job_mgmt.services.callback_service import send_callback

        execution = MagicMock()
        execution.callback_url = "http://example.com/callback"
        execution.id = 1
        execution.status = "success"
        execution.total_count = 3
        execution.success_count = 3
        execution.failed_count = 0
        execution.finished_at = datetime(2026, 4, 30, 10, 0, 0)

        with patch("apps.job_mgmt.services.callback_service.threading") as mock_threading:
            send_callback(execution)
            mock_threading.Thread.assert_called_once()
            mock_threading.Thread.return_value.start.assert_called_once()

    def test_do_callback_success_first_try(self):
        from apps.job_mgmt.services.callback_service import _do_callback

        with patch("apps.job_mgmt.services.callback_service.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            _do_callback("http://example.com/cb", {"task_id": 1}, 1)
            mock_post.assert_called_once()

    def test_do_callback_retries_on_failure(self):
        from apps.job_mgmt.services.callback_service import _do_callback

        with patch("apps.job_mgmt.services.callback_service.requests.post") as mock_post, patch(
            "apps.job_mgmt.services.callback_service.time.sleep"
        ) as mock_sleep:
            mock_post.return_value = MagicMock(status_code=500)
            _do_callback("http://example.com/cb", {"task_id": 1}, 1, max_retries=3)
            assert mock_post.call_count == 4  # initial + 3 retries
            assert mock_sleep.call_count == 3
            mock_sleep.assert_has_calls([call(1), call(2), call(4)])

    def test_do_callback_retries_on_exception(self):
        from apps.job_mgmt.services.callback_service import _do_callback

        with patch("apps.job_mgmt.services.callback_service.requests.post") as mock_post, patch("apps.job_mgmt.services.callback_service.time.sleep"):
            mock_post.side_effect = Exception("connection refused")
            _do_callback("http://example.com/cb", {"task_id": 1}, 1, max_retries=2)
            assert mock_post.call_count == 3  # initial + 2 retries

    def test_do_callback_stops_on_success(self):
        from apps.job_mgmt.services.callback_service import _do_callback

        with patch("apps.job_mgmt.services.callback_service.requests.post") as mock_post, patch("apps.job_mgmt.services.callback_service.time.sleep"):
            mock_post.side_effect = [
                MagicMock(status_code=500),
                MagicMock(status_code=200),
            ]
            _do_callback("http://example.com/cb", {"task_id": 1}, 1, max_retries=3)
            assert mock_post.call_count == 2  # failed once, succeeded second
