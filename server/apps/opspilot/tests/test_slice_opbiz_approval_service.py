"""opspilot-biz 切片: services/approval 人工审批信号（基于 django cache）。

审批存储的真实外部边界是 django cache。这里用真实 LocMemCache（settings 覆盖
DummyCache）以断言 set/get/delete 的真实副作用；wait_for_approval 的无人值守/超时/
轮询分支用真实逻辑驱动（mock cache.get 模拟用户决策、mock asyncio.sleep 加速）。
"""

import pytest

from apps.opspilot.services import approval
from apps.opspilot.services.approval import (
    _get_approval_cache_key,
    clear_approval_decision,
    get_approval_decision,
    submit_approval_decision,
    wait_for_approval,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def locmem_cache(settings):
    """用真实 LocMemCache 替换 conftest 注入的 DummyCache，使 set/get 生效。"""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "approval-test",
        }
    }
    from django.core.cache import cache

    cache.clear()
    yield cache
    cache.clear()


class TestCacheKey:
    def test_key_结构(self):
        assert _get_approval_cache_key("e1", "n1", "t1") == "approval:e1:n1:t1"


class TestSubmitGetClear:
    def test_提交后可读取(self, locmem_cache):
        payload = submit_approval_decision("e", "n", "t", "approve", reason="ok", decided_by="alice")
        assert payload["decision"] == "approve"
        assert payload["reason"] == "ok"
        assert payload["decided_by"] == "alice"
        assert isinstance(payload["decided_at"], int)
        # 真实落入 cache
        got = get_approval_decision("e", "n", "t")
        assert got["decision"] == "approve"
        assert got["decided_by"] == "alice"

    def test_清理后读取为None(self, locmem_cache):
        submit_approval_decision("e", "n", "t", "reject")
        clear_approval_decision("e", "n", "t")
        assert get_approval_decision("e", "n", "t") is None

    def test_未提交读取为None(self, locmem_cache):
        assert get_approval_decision("x", "y", "z") is None


@pytest.mark.asyncio
class TestWaitForApproval:
    async def test_无人值守_allow(self):
        out = await wait_for_approval("e", "n", "t", trigger_type="unattended", unattended_strategy="allow")
        assert out == {"decision": "approve", "reason": "无人值守自动策略: allow", "source": "auto"}

    async def test_无人值守_deny(self):
        out = await wait_for_approval("e", "n", "t", trigger_type="unattended", unattended_strategy="deny")
        assert out["decision"] == "reject"
        assert out["source"] == "auto"

    async def test_无人值守_skip(self):
        out = await wait_for_approval("e", "n", "t", trigger_type="unattended", unattended_strategy="other")
        assert out["decision"] == "skip"

    async def test_对话式_用户决策被消费(self, mocker):
        # 第一次轮询即返回用户决策
        mocker.patch.object(
            approval,
            "get_approval_decision",
            return_value={"decision": "approve", "reason": "go", "decided_by": "bob"},
        )
        clear_spy = mocker.patch.object(approval, "clear_approval_decision")
        out = await wait_for_approval("e", "n", "t", timeout_seconds=10)
        assert out == {"decision": "approve", "reason": "go", "source": "user", "decided_by": "bob"}
        # 消费后清理
        clear_spy.assert_called_once_with("e", "n", "t")

    async def test_超时降级_skip(self, mocker):
        mocker.patch.object(approval, "get_approval_decision", return_value=None)
        mocker.patch("apps.opspilot.services.approval.asyncio.sleep", new=mocker.AsyncMock())
        # timeout=0 → 立即越过 deadline
        out = await wait_for_approval("e", "n", "t", timeout_seconds=0, timeout_fallback="skip")
        assert out["decision"] == "skip"
        assert out["source"] == "timeout"

    async def test_超时降级_deny(self, mocker):
        mocker.patch.object(approval, "get_approval_decision", return_value=None)
        mocker.patch("apps.opspilot.services.approval.asyncio.sleep", new=mocker.AsyncMock())
        out = await wait_for_approval("e", "n", "t", timeout_seconds=0, timeout_fallback="deny")
        assert out["decision"] == "reject"
        assert out["source"] == "timeout"
