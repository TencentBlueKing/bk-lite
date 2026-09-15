"""GovernanceTaskHost.log 必须有单条输出和累计总额上限。"""

from unittest.mock import Mock

import pytest

from apps.node_mgmt.models import Node  # noqa: F401  包装器缺 node_mgmt 时补齐导入
from apps.patch_mgmt import config as patch_config
from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType
from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost
from apps.patch_mgmt.services import patch_execution_service as pes


ENTRY_LIMIT = 400
TOTAL_LIMIT = 900
TRUNCATED_MARK = "truncated"


def _make_host() -> GovernanceTaskHost:
    task = GovernanceTask.objects.create(
        name="host-log-budget",
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.RUNNING,
        team=[1],
    )
    return GovernanceTaskHost.objects.create(
        task=task,
        target_id=101,
        target_name="budget-host",
        target_ip="10.0.0.101",
    )


def _shrink_limits(monkeypatch) -> None:
    monkeypatch.setattr(patch_config, "HOST_EXECUTION_LOG_ENTRY_MAX_CHARS", ENTRY_LIMIT)
    monkeypatch.setattr(patch_config, "HOST_EXECUTION_LOG_TOTAL_MAX_CHARS", TOTAL_LIMIT)


@pytest.mark.django_db
def test_small_command_result_stays_intact(monkeypatch):
    _shrink_limits(monkeypatch)
    host = _make_host()
    warning_mock = Mock()
    monkeypatch.setattr(pes.logger, "warning", warning_mock)

    pes._append_host_log(
        host,
        "dnf update -y bash",
        {"stdout": "complete", "stderr": "", "exit_code": 0},
    )
    host.refresh_from_db()

    assert isinstance(host.log, str)
    assert "dnf update -y bash" in host.log
    assert "complete" in host.log
    assert "exit_code: 0" in host.log
    assert TRUNCATED_MARK not in host.log
    warning_mock.assert_not_called()


@pytest.mark.django_db
def test_oversized_stdout_is_bounded_and_keeps_head_tail_exit_code(monkeypatch):
    _shrink_limits(monkeypatch)
    host = _make_host()
    warning_mock = Mock()
    monkeypatch.setattr(pes.logger, "warning", warning_mock)
    stdout = "HEAD-TOKEN-" + ("x" * 4000) + "-TAIL-TOKEN"

    pes._append_host_log(
        host,
        "yum update -y kernel",
        {"stdout": stdout, "stderr": "warn-line", "error": "boom", "exit_code": 1},
    )
    host.refresh_from_db()

    assert isinstance(host.log, str)
    assert len(host.log) <= ENTRY_LIMIT
    assert TRUNCATED_MARK in host.log
    assert "HEAD-TOKEN-" in host.log
    assert "-TAIL-TOKEN" in host.log
    assert "exit_code: 1" in host.log
    assert "yum update -y kernel" in host.log
    warning_mock.assert_called_once()
    assert "event=patch_host_execution_log_truncated" in warning_mock.call_args.args[0]


@pytest.mark.django_db
def test_repeated_appends_do_not_grow_host_log_without_bound(monkeypatch):
    _shrink_limits(monkeypatch)
    host = _make_host()
    warning_mock = Mock()
    monkeypatch.setattr(pes.logger, "warning", warning_mock)

    for index in range(12):
        pes._append_host_log(
            host,
            f"check-{index}",
            {"stdout": f"chunk-{index}-" + ("n" * 80), "exit_code": index},
        )
        host.refresh_from_db()
        assert len(host.log) <= TOTAL_LIMIT

    assert isinstance(host.log, str)
    assert TRUNCATED_MARK in host.log
    assert "exit_code: 11" in host.log
    assert warning_mock.call_count >= 1
    assert all(
        call.args and "event=patch_host_execution_log_truncated" in call.args[0]
        for call in warning_mock.call_args_list
    )
