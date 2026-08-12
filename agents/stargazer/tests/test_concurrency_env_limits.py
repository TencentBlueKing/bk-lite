import pytest

from core.collection.application import (
    CollectionApplicationSettings,
    concurrency_limit_from_env,
)
from core.collection.constants import (
    DEFAULT_MAX_ACTIVE_TARGETS,
    DEFAULT_TARGET_TASK_WINDOW,
)
from core.collection.executor import TargetWorkerBudget
from core.collection.contracts import TargetExecutorSettings


def test_concurrency_limit_from_env_uses_default_and_zero_unlimited(monkeypatch):
    monkeypatch.delenv("MAX_ACTIVE_TARGETS", raising=False)
    assert (
        concurrency_limit_from_env("MAX_ACTIVE_TARGETS", DEFAULT_MAX_ACTIVE_TARGETS)
        == DEFAULT_MAX_ACTIVE_TARGETS
    )

    monkeypatch.setenv("MAX_ACTIVE_TARGETS", "3500")
    assert concurrency_limit_from_env("MAX_ACTIVE_TARGETS", DEFAULT_MAX_ACTIVE_TARGETS) == 3500

    monkeypatch.setenv("MAX_ACTIVE_TARGETS", "0")
    assert concurrency_limit_from_env("MAX_ACTIVE_TARGETS", DEFAULT_MAX_ACTIVE_TARGETS) == 0

    monkeypatch.setenv("MAX_ACTIVE_TARGETS", "-1")
    with pytest.raises(ValueError, match="MAX_ACTIVE_TARGETS"):
        concurrency_limit_from_env("MAX_ACTIVE_TARGETS", DEFAULT_MAX_ACTIVE_TARGETS)


def test_application_settings_from_env_reads_concurrency(monkeypatch):
    monkeypatch.setenv("MAX_ACTIVE_TARGETS", "0")
    monkeypatch.setenv("TARGET_TASK_WINDOW", "0")
    settings = CollectionApplicationSettings.from_env()
    assert settings.max_active_targets == 0
    assert settings.target_task_window == 0

    monkeypatch.delenv("MAX_ACTIVE_TARGETS", raising=False)
    monkeypatch.delenv("TARGET_TASK_WINDOW", raising=False)
    settings = CollectionApplicationSettings.from_env()
    assert settings.max_active_targets == DEFAULT_MAX_ACTIVE_TARGETS
    assert settings.target_task_window == DEFAULT_TARGET_TASK_WINDOW


def test_target_executor_settings_allow_zero_unlimited():
    settings = TargetExecutorSettings(max_active_targets=0, target_task_window=0)
    assert settings.max_active_targets == 0
    assert settings.target_task_window == 0


@pytest.mark.asyncio
async def test_worker_budget_zero_means_unlimited():
    budget = TargetWorkerBudget(0)
    reserved = await budget.reserve(12)
    assert reserved == 12
    assert budget.active == 12
    await budget.release(12)
    assert budget.active == 0
