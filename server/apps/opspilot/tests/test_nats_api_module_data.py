"""
Tests for get_opspilot_module_data NATS handler — Issue #3433
Validates that unknown module/child_module values return structured error
instead of raising KeyError.
"""
import sys
import importlib.util
import types
from pathlib import Path


def _install(name, **attrs):
    """Install a stub module into sys.modules."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _install_submodule(parent_name, child_name, **attrs):
    parent = sys.modules.get(parent_name)
    if parent is None:
        parent = _install(parent_name)
    full_name = f"{parent_name}.{child_name}"
    mod = _install(full_name, **attrs)
    setattr(parent, child_name, mod)
    return mod


def _make_queryset_stub(items=None):
    """Return a stub that behaves like a Django QuerySet for our needs."""
    items = items or []

    class _QS:
        def filter(self, **kwargs):
            return self

        def count(self):
            return len(items)

        def __getitem__(self, slc):
            return items[slc]

        def values(self, *fields):
            return self

    return _QS()


def _make_model_stub(queryset):
    class _Model:
        objects = queryset

    return _Model


def _load_nats_api():
    """
    Load server/apps/opspilot/nats_api.py in isolation via exec_module,
    injecting all required stubs so Django settings are never touched.
    """
    # ── nats_client stub ──────────────────────────────────────────────
    registered_handlers = {}

    def register(fn):
        registered_handlers[fn.__name__] = fn
        return fn

    nats_client_stub = _install("nats_client", register=register)

    # ── django.db stubs ───────────────────────────────────────────────
    _install("django")
    _install("django.db")
    _install("django.db.models")

    # ── Stub model classes ────────────────────────────────────────────
    qs_stub = _make_queryset_stub()

    def _model(name):
        return _make_model_stub(qs_stub)

    Bot = _model("Bot")
    LLMSkill = _model("LLMSkill")
    SkillTools = _model("SkillTools")
    LLMModel = _model("LLMModel")
    OCRProvider = _model("OCRProvider")
    EmbedProvider = _model("EmbedProvider")
    RerankProvider = _model("RerankProvider")

    models_stub = _install(
        "apps.opspilot.models",
        Bot=Bot,
        BotConversationHistory=object,
        BotWorkFlow=object,
        EmbedProvider=EmbedProvider,
        LLMModel=LLMModel,
        LLMSkill=LLMSkill,
        OCRProvider=OCRProvider,
        RerankProvider=RerankProvider,
        SkillTools=SkillTools,
    )

    # ── Other transitive stubs ────────────────────────────────────────
    _install("apps")
    _install("apps.core")
    _install("apps.core.logger", opspilot_logger=__import__("logging").getLogger("test"))
    _install("apps.opspilot")
    _install("apps.opspilot.utils")
    _install("apps.opspilot.utils.bot_utils", get_user_info=lambda *a, **kw: (None, None))
    _install("apps.opspilot.utils.chat_flow_utils")
    _install("apps.opspilot.utils.chat_flow_utils.engine")
    _install(
        "apps.opspilot.utils.chat_flow_utils.engine.factory",
        create_chat_flow_engine=lambda *a, **kw: None,
    )

    # ── Load the actual module ────────────────────────────────────────
    src = Path(__file__).parent.parent / "nats_api.py"
    spec = importlib.util.spec_from_file_location("opspilot_nats_api", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    return mod, registered_handlers


class TestGetOpspilotModuleDataBoundary:
    """Issue #3433: unknown module/child_module must not raise KeyError."""

    @classmethod
    def setup_class(cls):
        cls.mod, cls.handlers = _load_nats_api()

    def _call(self, module, child_module="", page=1, page_size=10, group_id=1):
        fn = self.handlers["get_opspilot_module_data"]
        return fn(module=module, child_module=child_module, page=page, page_size=page_size, group_id=group_id)

    # ── R1: unknown top-level module ──────────────────────────────────
    def test_unknown_module_returns_error_not_keyerror(self):
        result = self._call(module="nonexistent_module")
        assert result["result"] is False, "Expected result=False for unknown module"
        assert "Unknown module" in result["message"]

    # ── R2: unknown provider child_module ─────────────────────────────
    def test_unknown_child_module_returns_error_not_keyerror(self):
        result = self._call(module="provider", child_module="nonexistent_child")
        assert result["result"] is False, "Expected result=False for unknown child_module"
        assert "Unknown child_module" in result["message"]

    # ── Regression: known modules must still work ─────────────────────
    def test_known_module_bot_succeeds(self):
        result = self._call(module="bot")
        assert "count" in result
        assert "items" in result

    def test_known_module_skill_succeeds(self):
        result = self._call(module="skill")
        assert "count" in result

    def test_known_module_tools_succeeds(self):
        result = self._call(module="tools")
        assert "count" in result

    def test_known_provider_llm_model_succeeds(self):
        result = self._call(module="provider", child_module="llm_model")
        assert "count" in result

    def test_known_provider_ocr_model_succeeds(self):
        result = self._call(module="provider", child_module="ocr_model")
        assert "count" in result

    # ── Revert guard: empty string module also triggers error ──────────
    def test_empty_string_module_returns_error(self):
        result = self._call(module="")
        assert result["result"] is False

    def test_empty_string_child_module_returns_error(self):
        result = self._call(module="provider", child_module="")
        assert result["result"] is False
