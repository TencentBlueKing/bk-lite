"""
Tests for consume_bot_event NATS handler — Issue #3721
Validates that missing bot_id returns an explicit error instead of silently
writing conversation history to the hardcoded Bot #7.
"""
import sys
import importlib.util
import types
from pathlib import Path

_MISSING = object()


def _install(name, originals=None, **attrs):
    if originals is not None and name not in originals:
        originals[name] = sys.modules.get(name, _MISSING)
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _restore_modules(originals):
    for name, original in reversed(list(originals.items())):
        if original is _MISSING:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


def _load_nats_api():
    """
    Load server/apps/opspilot/nats_api.py in isolation via exec_module,
    injecting all required stubs so Django settings are never touched.
    """
    registered_handlers = {}
    originals = {}

    def install(name, **attrs):
        return _install(name, originals, **attrs)

    def register(fn):
        registered_handlers[fn.__name__] = fn
        return fn

    install("nats_client", register=register)
    install("django")
    install("django.db")
    install("django.db.models")

    # Track Bot.objects.get calls so we can assert Bot #7 is never queried
    bot_get_calls = []

    class _BotObjects:
        def get(self, **kwargs):
            bot_get_calls.append(kwargs)
            raise _BotDoesNotExist(f"Bot matching query does not exist: {kwargs}")

    class _BotDoesNotExist(Exception):
        pass

    class _Bot:
        DoesNotExist = _BotDoesNotExist
        objects = _BotObjects()

    # Track BotConversationHistory.objects.create calls
    history_create_calls = []

    class _HistoryObjects:
        def create(self, **kwargs):
            history_create_calls.append(kwargs)

    class _BotConversationHistory:
        objects = _HistoryObjects()

    class _QS:
        def filter(self, **kwargs):
            return self
        def order_by(self, *a):
            return self
        def first(self):
            return None

    class _BotWorkFlow:
        objects = _QS()

    install(
        "apps.opspilot.models",
        Bot=_Bot,
        BotConversationHistory=_BotConversationHistory,
        BotWorkFlow=_BotWorkFlow,
        EmbedProvider=object,
        KnowledgeBase=object,
        LLMModel=object,
        LLMSkill=object,
        OCRProvider=object,
        RerankProvider=object,
        SkillTools=object,
    )
    install("apps")
    install("apps.core")
    install("apps.core.logger", opspilot_logger=__import__("logging").getLogger("test"))
    install("apps.opspilot")
    install("apps.opspilot.utils")
    install("apps.opspilot.utils.bot_utils", get_user_info=lambda *a, **kw: (types.SimpleNamespace(id=1), None))
    install("apps.opspilot.utils.chat_flow_utils")
    install("apps.opspilot.utils.chat_flow_utils.engine")
    install(
        "apps.opspilot.utils.chat_flow_utils.engine.factory",
        create_chat_flow_engine=lambda *a, **kw: None,
    )

    src = Path(__file__).parent.parent / "nats_api.py"
    spec = importlib.util.spec_from_file_location("opspilot_nats_api_3721", src)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    finally:
        _restore_modules(originals)

    return mod, registered_handlers, bot_get_calls, history_create_calls


class TestConsumeBotEventBotIdRequired:
    """Issue #3721: missing bot_id must be rejected explicitly, not silently written to Bot #7."""

    @classmethod
    def setup_class(cls):
        cls.mod, cls.handlers, cls.bot_get_calls, cls.history_create_calls = _load_nats_api()

    def _call(self, **kwargs):
        fn = self.handlers["consume_bot_event"]
        return fn(kwargs)

    # ── Core fix: absent bot_id must return error ─────────────────────
    def test_missing_bot_id_returns_error(self):
        result = self._call(
            text="hello",
            sender_id="user_abc",
            timestamp=1700000000.0,
            event="user",
            input_channel="web",
        )
        assert result["result"] is False, "Expected result=False when bot_id is absent"
        assert "bot_id" in result.get("message", "").lower(), (
            f"Error message should mention bot_id; got: {result.get('message')}"
        )

    def test_none_bot_id_returns_error(self):
        result = self._call(
            text="hello",
            sender_id="user_abc",
            timestamp=1700000000.0,
            event="user",
            input_channel="web",
            bot_id=None,
        )
        assert result["result"] is False, "Expected result=False when bot_id is None"

    def test_zero_bot_id_returns_error(self):
        """bot_id=0 is falsy and should also be rejected (0 is not a valid Bot pk)."""
        result = self._call(
            text="hello",
            sender_id="user_abc",
            timestamp=1700000000.0,
            event="user",
            input_channel="web",
            bot_id=0,
        )
        assert result["result"] is False, "Expected result=False when bot_id is 0"

    # ── Revert guard: Bot #7 must never be queried when bot_id is absent ─
    def test_bot7_not_queried_when_bot_id_missing(self):
        initial_calls = len(self.bot_get_calls)
        self._call(
            text="hello",
            sender_id="user_xyz",
            timestamp=1700000000.0,
            event="user",
            input_channel="web",
        )
        new_calls = self.bot_get_calls[initial_calls:]
        bot7_calls = [c for c in new_calls if c.get("id") == 7]
        assert not bot7_calls, (
            f"Bot #7 was queried despite missing bot_id — hardcoded default is back: {bot7_calls}"
        )

    # ── Regression: empty text short-circuits before bot_id check ──────
    def test_empty_text_returns_ok_without_touching_bot(self):
        result = self._call(
            text="",
            sender_id="user_abc",
            timestamp=1700000000.0,
            event="user",
            input_channel="web",
        )
        # empty text → early return True (existing behaviour preserved)
        assert result["result"] is True

    # ── Regression: whitespace-only sender_id short-circuits ───────────
    def test_blank_sender_id_returns_ok_without_touching_bot(self):
        result = self._call(
            text="hello",
            sender_id="   ",
            timestamp=1700000000.0,
            event="user",
            input_channel="web",
        )
        assert result["result"] is True

    # ── Regression: non-integer bot_id returns structured error ────────
    def test_non_integer_bot_id_returns_error(self):
        result = self._call(
            text="hello",
            sender_id="user_abc",
            timestamp=1700000000.0,
            event="user",
            input_channel="web",
            bot_id="not_a_number",
        )
        assert result["result"] is False
