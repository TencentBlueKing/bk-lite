"""
wait_for_choice 等待策略的单元测试（2026-06-18 变更）。

覆盖：
- unattended：立即用默认值（不长等待）
- interactive：有答案→user；被中断→interrupted；不再因超时回退默认
- third_party：保留有界等待，超时→默认（不悬挂 webhook）

用 mock 控制 get_user_choice / is_interrupt_requested_async，避免真实 cache 与死循环。
bot_id/session_id 传 None 以跳过 pending 续租（续租逻辑由 test_pending_hitl 覆盖）。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.opspilot.utils.user_choice import wait_for_choice

pytestmark = pytest.mark.unit

OPTIONS = [{"key": "a", "label": "A"}, {"key": "b", "label": "B"}]


async def test_unattended_returns_default_immediately():
    result = await wait_for_choice("exec1", "nodeB", "c1", OPTIONS, default_keys=["b"], trigger_type="unattended")
    assert result == {"selected": ["b"], "source": "auto"}


async def test_interactive_returns_user_answer():
    with (
        patch("apps.opspilot.utils.user_choice.get_user_choice", MagicMock(return_value={"selected": ["x"]})),
        patch("apps.opspilot.utils.user_choice.clear_user_choice", MagicMock()),
    ):
        result = await wait_for_choice("exec1", "nodeB", "c1", OPTIONS, default_keys=["a"], trigger_type="interactive")
    assert result == {"selected": ["x"], "source": "user"}


async def test_interactive_returns_interrupted_when_no_answer():
    with (
        patch("apps.opspilot.utils.user_choice.get_user_choice", MagicMock(return_value=None)),
        patch(
            "apps.opspilot.utils.execution_interrupt.is_interrupt_requested_async",
            AsyncMock(return_value=True),
        ),
    ):
        result = await wait_for_choice("exec1", "nodeB", "c1", OPTIONS, default_keys=["a"], trigger_type="interactive")
    assert result == {"selected": [], "source": "interrupted"}


async def test_third_party_bounded_wait_times_out_to_default():
    # timeout_seconds=0 → 有界循环立即到期 → 回退默认，不悬挂
    with (
        patch("apps.opspilot.utils.user_choice.get_user_choice", MagicMock(return_value=None)),
        patch(
            "apps.opspilot.utils.execution_interrupt.is_interrupt_requested_async",
            AsyncMock(return_value=False),
        ),
    ):
        result = await wait_for_choice(
            "exec1",
            "nodeB",
            "c1",
            OPTIONS,
            default_keys=["a"],
            timeout_seconds=0,
            trigger_type="third_party",
        )
    assert result == {"selected": ["a"], "source": "timeout"}
