"""
pending_hitl 会话级注册表 + 入口投递 helper 的单元测试。

注意：全局 conftest 的 autouse fixture 把 cache 换成 DummyCache（永不存储），
本模块按 fixture 名覆盖回 LocMemCache，以验证真实的 register/get/clear/投递行为。
"""

import pytest

from apps.opspilot.utils.pending_hitl import clear_pending, get_pending, register_pending, try_deliver_to_pending
from apps.opspilot.utils.user_choice import get_user_choice


@pytest.fixture(autouse=True)
def use_locmem_cache_backend(settings):
    """覆盖全局 DummyCache：本模块需要真实可读写的 cache。"""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-pending-hitl",
        }
    }
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


pytestmark = pytest.mark.unit


def test_register_then_get_returns_payload():
    register_pending("bot1", "sess1", execution_id="exec1", node_id="nodeB", choice_id="c1")
    pending = get_pending("bot1", "sess1")
    assert pending is not None
    assert pending["execution_id"] == "exec1"
    assert pending["node_id"] == "nodeB"
    assert pending["choice_id"] == "c1"
    assert pending["kind"] == "choice"


def test_clear_removes_pending():
    register_pending("bot1", "sess1", execution_id="exec1", node_id="nodeB", choice_id="c1")
    clear_pending("bot1", "sess1")
    assert get_pending("bot1", "sess1") is None


def test_register_noop_without_bot_or_session():
    assert register_pending("", "sess1", execution_id="e", node_id="n", choice_id="c") is None
    assert register_pending("bot1", "", execution_id="e", node_id="n", choice_id="c") is None
    assert get_pending("", "sess1") is None
    assert get_pending("bot1", "") is None


def test_pending_is_scoped_per_bot_session():
    register_pending("bot1", "sessA", execution_id="execA", node_id="n", choice_id="c")
    assert get_pending("bot1", "sessB") is None
    assert get_pending("bot2", "sessA") is None
    assert get_pending("bot1", "sessA") is not None


def test_try_deliver_hit_writes_choice_and_clears_pending():
    register_pending("bot1", "sess1", execution_id="exec1", node_id="nodeB", choice_id="c1")

    delivered = try_deliver_to_pending("bot1", "sess1", "用户的自由文本回答")

    assert delivered is not None
    assert delivered["delivered_to_pending"] is True
    assert delivered["execution_id"] == "exec1"
    assert delivered["node_id"] == "nodeB"
    assert delivered["choice_id"] == "c1"

    # 答案已写入选择通道，等待中的 wait_for_choice 轮询会命中
    choice = get_user_choice("exec1", "nodeB", "c1")
    assert choice is not None
    assert choice["selected"] == ["用户的自由文本回答"]

    # pending 已清理（避免重复投递）
    assert get_pending("bot1", "sess1") is None


def test_try_deliver_miss_returns_none():
    assert try_deliver_to_pending("bot1", "no-such-session", "hi") is None
