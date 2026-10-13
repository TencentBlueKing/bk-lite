"""会话级阻塞投递已删除，回复改为新一轮续接。"""

from apps.opspilot.utils.pending_question import resolve_conversation_key


def test_pending_delivery_module_removed_and_key_stays_stable():
    import importlib

    with __import__("pytest").raises(ModuleNotFoundError):
        importlib.import_module("apps.opspilot.utils.pending_hitl")
    assert resolve_conversation_key(bot_id="9", session_id="sess") == "flow:9:sess"
