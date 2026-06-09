"""
Tests for fix-channel-message-dedup-and-async (Issues #3090, #3091).

Issue #3090: 钉钉消息去重竞态条件修复
- DingTalkChatFlowUtils 继承 BaseChatFlowUtils
- 使用原子操作 cache.add() 替代非原子 get/set
- cache_key_prefix 设置正确

Issue #3091: 微信公众号异步处理缺失修复
- process_wechat_official_message Celery 任务存在
- WechatOfficialChatFlowUtils 使用 Celery .delay() 而非不存在的 process_message_async
- 正确继承 BaseChatFlowUtils

验证方式：源码分析 + 继承关系检查 + 属性验证
"""

import inspect
import sys
import types

# C-extension stubs
for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
_falkordb.Graph = type("Graph", (), {})
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
_falkordb_asyncio.FalkorDB = type("FalkorDB", (), {})
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)

from apps.opspilot.utils.base_chat_flow_utils import BaseChatFlowUtils  # noqa: E402

# ---------------------------------------------------------------------------
# Test Group 1: DingTalk Inheritance and Atomic Dedup (Issue #3090)
# ---------------------------------------------------------------------------


class TestDingTalkInheritanceFix:
    """Tests for DingTalk message dedup race condition fix (Issue #3090)."""

    def test_dingtalk_inherits_base_chat_flow_utils(self):
        """TC-3090-01: DingTalkChatFlowUtils must inherit BaseChatFlowUtils."""
        from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils

        assert issubclass(DingTalkChatFlowUtils, BaseChatFlowUtils), "DingTalkChatFlowUtils must inherit BaseChatFlowUtils for atomic dedup"

    def test_dingtalk_has_correct_channel_attributes(self):
        """TC-3090-02: DingTalkChatFlowUtils must have correct channel attributes."""
        from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils

        assert DingTalkChatFlowUtils.channel_name == "钉钉"
        assert DingTalkChatFlowUtils.channel_code == "dingtalk"
        assert DingTalkChatFlowUtils.cache_key_prefix == "dingtalk_msg"

    def test_dingtalk_cache_key_format_compatible(self):
        """TC-3090-03: Cache key format must be dingtalk_msg:{bot_id}:{msg_id}."""
        from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils

        # Verify cache key format via source analysis of base class
        source = inspect.getsource(BaseChatFlowUtils.is_message_processed)
        assert 'f"{self.cache_key_prefix}:{self.bot_id}:{msg_id}"' in source, "Cache key format must be {prefix}:{bot_id}:{msg_id}"

        # Verify DingTalk prefix
        assert DingTalkChatFlowUtils.cache_key_prefix == "dingtalk_msg"

    def test_dingtalk_uses_atomic_cache_add(self):
        """TC-3090-04: DingTalk must use cache.add() via BaseChatFlowUtils for atomic dedup."""
        from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils

        # Verify inheritance (DingTalk uses base class method)
        assert (
            DingTalkChatFlowUtils.is_message_processed is BaseChatFlowUtils.is_message_processed
        ), "DingTalk should inherit is_message_processed from BaseChatFlowUtils"

        # Verify base class uses cache.add()
        source = inspect.getsource(BaseChatFlowUtils.is_message_processed)
        assert "cache.add(" in source, "BaseChatFlowUtils.is_message_processed must use cache.add()"

    def test_dingtalk_no_duplicate_dedup_methods(self):
        """TC-3090-05: DingTalk must not override dedup methods (use base class)."""
        from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils

        # These methods should be inherited, not overridden
        assert DingTalkChatFlowUtils.is_message_processed is BaseChatFlowUtils.is_message_processed
        assert DingTalkChatFlowUtils.mark_message_completed is BaseChatFlowUtils.mark_message_completed
        assert DingTalkChatFlowUtils.mark_message_failed is BaseChatFlowUtils.mark_message_failed

    def test_dingtalk_implements_send_reply(self):
        """TC-3090-06: DingTalk must implement abstract send_reply method."""
        from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils

        # send_reply should be overridden (not the base class abstract method)
        assert DingTalkChatFlowUtils.send_reply is not BaseChatFlowUtils.send_reply, "DingTalk must implement send_reply abstract method"

        # Verify it's callable
        assert callable(DingTalkChatFlowUtils.send_reply)


# ---------------------------------------------------------------------------
# Test Group 2: WeChat Official Celery Task and Async Processing (Issue #3091)
# ---------------------------------------------------------------------------


class TestWechatOfficialAsyncFix:
    """Tests for WeChat Official async processing fix (Issue #3091)."""

    def test_wechat_official_celery_task_exists(self):
        """TC-3091-01: process_wechat_official_message Celery task must exist."""
        from apps.opspilot.tasks import process_wechat_official_message

        assert callable(process_wechat_official_message), "process_wechat_official_message Celery task must exist"

    def test_wechat_official_celery_task_is_shared_task(self):
        """TC-3091-02: process_wechat_official_message must be a Celery shared_task."""
        from apps.opspilot.tasks import process_wechat_official_message

        # Celery tasks have these attributes
        assert hasattr(process_wechat_official_message, "delay"), "Celery task must have .delay() method"
        assert hasattr(process_wechat_official_message, "apply_async"), "Celery task must have .apply_async() method"

    def test_wechat_official_celery_task_signature(self):
        """TC-3091-03: Celery task must accept (bot_id, msg_id, message, sender_id, config)."""
        from apps.opspilot import tasks

        # Use source analysis since inspect.signature on Celery tasks may vary
        source = inspect.getsource(tasks.process_wechat_official_message)

        # Check function definition line contains expected parameters
        assert (
            "def process_wechat_official_message(self, bot_id, msg_id, message, sender_id, config)" in source
        ), "Task must have signature (self, bot_id, msg_id, message, sender_id, config)"

    def test_wechat_official_no_process_message_async_call(self):
        """TC-3091-04: handle_wechat_message must NOT call non-existent process_message_async."""
        from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils

        source = inspect.getsource(WechatOfficialChatFlowUtils.handle_wechat_message)

        # Check there's no actual method call to process_message_async
        # Note: comments mentioning it are OK, actual calls are not
        # A call would look like: self.process_message_async( or process_message_async(
        # Match actual method calls, not comments
        # call_pattern = r"(?<!#.*)\bprocess_message_async\s*\("
        # Split by lines and check non-comment lines
        for line in source.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # Skip comment lines
            if "process_message_async(" in stripped and not stripped.startswith("#"):
                # Check if it's in a comment on the same line
                if "#" in stripped:
                    code_part = stripped.split("#")[0]
                    if "process_message_async(" in code_part:
                        raise AssertionError("handle_wechat_message must not call non-existent process_message_async")
                else:
                    raise AssertionError("handle_wechat_message must not call non-existent process_message_async")

    def test_wechat_official_uses_celery_delay(self):
        """TC-3091-05: handle_wechat_message must use Celery .delay() for async processing."""
        from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils

        source = inspect.getsource(WechatOfficialChatFlowUtils.handle_wechat_message)

        assert "process_wechat_official_message.delay(" in source, "handle_wechat_message must use process_wechat_official_message.delay()"

    def test_wechat_official_imports_celery_task(self):
        """TC-3091-06: wechat_official_chat_flow_utils must import the Celery task."""
        from apps.opspilot.services import wechat_official_chat_flow_utils

        source = inspect.getsource(wechat_official_chat_flow_utils)

        assert "from apps.opspilot.tasks import process_wechat_official_message" in source, "Must import process_wechat_official_message from tasks"

    def test_wechat_official_inherits_base_chat_flow_utils(self):
        """TC-3091-07: WechatOfficialChatFlowUtils must inherit BaseChatFlowUtils."""
        from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils

        assert issubclass(WechatOfficialChatFlowUtils, BaseChatFlowUtils), "WechatOfficialChatFlowUtils must inherit BaseChatFlowUtils"

    def test_wechat_official_has_correct_channel_attributes(self):
        """TC-3091-08: WechatOfficialChatFlowUtils must have correct channel attributes."""
        from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils

        assert WechatOfficialChatFlowUtils.channel_name == "微信公众号"
        assert WechatOfficialChatFlowUtils.channel_code == "wechat_official_account"
        assert WechatOfficialChatFlowUtils.cache_key_prefix == "wechat_official_msg"

    def test_wechat_official_implements_send_reply(self):
        """TC-3091-09: WechatOfficialChatFlowUtils must implement send_reply."""
        from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils

        assert WechatOfficialChatFlowUtils.send_reply is not BaseChatFlowUtils.send_reply, "WechatOfficialChatFlowUtils must implement send_reply"

    def test_wechat_official_uses_base_dedup(self):
        """TC-3091-10: WechatOfficialChatFlowUtils must use base class dedup (is_message_processed)."""
        from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils

        source = inspect.getsource(WechatOfficialChatFlowUtils.handle_wechat_message)

        assert "self.is_message_processed(" in source, "handle_wechat_message must call self.is_message_processed() for dedup"


# ---------------------------------------------------------------------------
# Test Group 3: All Channels Consistent Inheritance Pattern
# ---------------------------------------------------------------------------


class TestAllChannelsConsistentPattern:
    """Tests for consistent inheritance pattern across all channels."""

    def test_all_channels_inherit_base_chat_flow_utils(self):
        """TC-COMMON-01: All channel utils must inherit BaseChatFlowUtils."""
        from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils
        from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils

        channels = [
            ("DingTalk", DingTalkChatFlowUtils),
            ("WechatOfficial", WechatOfficialChatFlowUtils),
        ]

        for name, cls in channels:
            assert issubclass(cls, BaseChatFlowUtils), f"{name} must inherit BaseChatFlowUtils"

    def test_all_channels_have_required_attributes(self):
        """TC-COMMON-02: All channels must define channel_name, channel_code, cache_key_prefix."""
        from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils
        from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils

        channels = [
            ("DingTalk", DingTalkChatFlowUtils),
            ("WechatOfficial", WechatOfficialChatFlowUtils),
        ]

        for name, cls in channels:
            assert cls.channel_name, f"{name} must have channel_name"
            assert cls.channel_code, f"{name} must have channel_code"
            assert cls.cache_key_prefix, f"{name} must have cache_key_prefix"

    def test_all_channels_use_atomic_dedup(self):
        """TC-COMMON-03: All channels must use atomic cache.add() via base class."""
        from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils
        from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils

        channels = [
            ("DingTalk", DingTalkChatFlowUtils),
            ("WechatOfficial", WechatOfficialChatFlowUtils),
        ]

        for name, cls in channels:
            # Should inherit is_message_processed from base class
            assert (
                cls.is_message_processed is BaseChatFlowUtils.is_message_processed
            ), f"{name} must use BaseChatFlowUtils.is_message_processed for atomic dedup"

    def test_all_channels_implement_send_reply(self):
        """TC-COMMON-04: All channels must implement abstract send_reply method."""
        from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils
        from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils

        channels = [
            ("DingTalk", DingTalkChatFlowUtils),
            ("WechatOfficial", WechatOfficialChatFlowUtils),
        ]

        for name, cls in channels:
            assert cls.send_reply is not BaseChatFlowUtils.send_reply, f"{name} must implement send_reply abstract method"

    def test_cache_key_prefixes_are_unique(self):
        """TC-COMMON-05: Each channel must have unique cache_key_prefix."""
        from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils
        from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils

        prefixes = [
            DingTalkChatFlowUtils.cache_key_prefix,
            WechatOfficialChatFlowUtils.cache_key_prefix,
        ]

        assert len(prefixes) == len(set(prefixes)), "Each channel must have unique cache_key_prefix to avoid key collision"


# ---------------------------------------------------------------------------
# Test Group 4: Celery Task Configuration
# ---------------------------------------------------------------------------


class TestCeleryTaskConfiguration:
    """Tests for Celery task configuration."""

    def test_wechat_official_task_has_retry_config(self):
        """TC-CELERY-01: process_wechat_official_message must have retry configuration."""
        from apps.opspilot.tasks import process_wechat_official_message

        # Check task has max_retries configured
        assert hasattr(process_wechat_official_message, "max_retries"), "Task must have max_retries configured"

    def test_wechat_official_task_calls_handler(self):
        """TC-CELERY-02: Celery task must call WechatOfficialChatFlowUtils."""
        from apps.opspilot import tasks

        source = inspect.getsource(tasks.process_wechat_official_message)

        assert "WechatOfficialChatFlowUtils" in source, "Task must use WechatOfficialChatFlowUtils"

    def test_wechat_official_task_calls_async_process_and_reply(self):
        """TC-CELERY-03: Celery task must call async_process_and_reply method."""
        from apps.opspilot import tasks

        source = inspect.getsource(tasks.process_wechat_official_message)

        assert "async_process_and_reply" in source, "Task must call async_process_and_reply method"

    def test_all_channel_tasks_exist(self):
        """TC-CELERY-04: All channels must have corresponding Celery tasks."""
        from apps.opspilot import tasks

        # Verify all channel tasks exist
        assert hasattr(tasks, "process_wechat_message"), "process_wechat_message task must exist"
        assert hasattr(tasks, "process_dingtalk_message"), "process_dingtalk_message task must exist"
        assert hasattr(tasks, "process_wechat_official_message"), "process_wechat_official_message task must exist"

    def test_all_channel_tasks_are_celery_tasks(self):
        """TC-CELERY-05: All channel tasks must be Celery shared_tasks."""
        from apps.opspilot.tasks import process_dingtalk_message, process_wechat_message, process_wechat_official_message

        tasks_to_check = [
            ("process_wechat_message", process_wechat_message),
            ("process_dingtalk_message", process_dingtalk_message),
            ("process_wechat_official_message", process_wechat_official_message),
        ]

        for name, task in tasks_to_check:
            assert hasattr(task, "delay"), f"{name} must have .delay() method"
            assert hasattr(task, "apply_async"), f"{name} must have .apply_async() method"


# ---------------------------------------------------------------------------
# Test Group 5: Base Class Atomic Operation Verification
# ---------------------------------------------------------------------------


class TestBaseChatFlowUtilsAtomicOperation:
    """Tests for BaseChatFlowUtils atomic operation implementation."""

    def test_is_message_processed_uses_cache_add(self):
        """TC-BASE-01: is_message_processed must use cache.add() for atomic acquisition."""
        source = inspect.getsource(BaseChatFlowUtils.is_message_processed)

        assert "cache.add(" in source, "is_message_processed must use cache.add() for atomic lock acquisition"

    def test_is_message_processed_checks_status_first(self):
        """TC-BASE-02: is_message_processed must check existing status before add()."""
        source = inspect.getsource(BaseChatFlowUtils.is_message_processed)

        # Should check for "completed" and "processing" status first
        assert 'status == "completed"' in source, "Must check for completed status"
        assert 'status == "processing"' in source, "Must check for processing status"

    def test_is_message_processed_returns_correct_values(self):
        """TC-BASE-03: is_message_processed return values must be correct."""
        source = inspect.getsource(BaseChatFlowUtils.is_message_processed)

        # When completed or processing, return True (skip)
        # When acquired via add(), return False (can process)
        # When add() fails, return True (skip)
        assert "return True" in source
        assert "return False" in source

    def test_mark_message_completed_uses_cache_set(self):
        """TC-BASE-04: mark_message_completed must use cache.set() with long TTL."""
        source = inspect.getsource(BaseChatFlowUtils.mark_message_completed)

        assert "cache.set(" in source, "mark_message_completed must use cache.set()"
        assert '"completed"' in source, "Must set status to 'completed'"
        assert "MESSAGE_COMPLETED_EXPIRE_SECONDS" in source, "Must use MESSAGE_COMPLETED_EXPIRE_SECONDS TTL"

    def test_mark_message_failed_uses_cache_delete(self):
        """TC-BASE-05: mark_message_failed must use cache.delete() to allow retry."""
        source = inspect.getsource(BaseChatFlowUtils.mark_message_failed)

        assert "cache.delete(" in source, "mark_message_failed must use cache.delete()"
