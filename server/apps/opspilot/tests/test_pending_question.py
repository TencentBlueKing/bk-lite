"""终止式提问的会话标记：写入、一次性消费、过期与证据顺序。"""

import logging

import pytest
from django.test import override_settings
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from apps.opspilot.utils.pending_question import (
    consume_pending_question,
    format_choice_text,
    is_answer_after_choice_prompt,
    resolve_conversation_key,
    save_pending_question,
    splice_evidence_messages,
)

_LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "pending-question-tests",
    }
}


@pytest.fixture(autouse=True)
def _locmem_cache():
    with override_settings(CACHES=_LOCMEM):
        from django.core.cache import cache

        cache.clear()
        yield
        cache.clear()


@pytest.mark.django_db
def test_resolve_conversation_key_for_four_entries():
    assert resolve_conversation_key(bot_id=3, session_id="s-1") == "flow:3:s-1"
    assert resolve_conversation_key(skill_session_id="skill-session") == "skill:skill-session"
    assert resolve_conversation_key(thread_id="thread-debug") == "thread:thread-debug"
    assert resolve_conversation_key(session_id="studio-session") == "session:studio-session"
    assert resolve_conversation_key() == ""
    assert resolve_conversation_key(bot_id=3) == ""


@pytest.mark.django_db
def test_pending_question_is_consumed_once_and_logs_tokens_only(caplog):
    question = "请选择集群"
    evidence = [
        AIMessage(content="", tool_calls=[{"id": "call-1", "name": "list_clusters", "args": {}}]),
        ToolMessage(content="cluster-a", tool_call_id="call-1", name="list_clusters"),
    ]
    caplog.set_level(logging.INFO)
    saved = save_pending_question(
        "thread:debug",
        {
            "kind": "user_choice",
            "execution_id": "exec-1",
            "node_id": "agent-b",
            "question": question,
            "options": [{"key": "cluster-a", "label": "cluster-a"}],
            "question_text": format_choice_text(question, "single_select", ["cluster-a"]),
            "evidence_messages": [],
        },
    )
    saved["evidence_messages"] = []
    first = consume_pending_question("thread:debug")
    second = consume_pending_question("thread:debug")

    assert first["kind"] == "user_choice"
    assert first["node_id"] == "agent-b"
    assert second is None
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "event=pending_question_saved" in rendered
    assert "event=pending_question_hit" in rendered
    assert "evidence_tokens=" in rendered
    assert question not in rendered
    assert "cluster-a" not in rendered
    assert evidence[1].content not in rendered


@pytest.mark.django_db
def test_expired_pending_question_degrades_quietly(caplog):
    save_pending_question(
        "flow:1:s",
        {
            "kind": "limit_continue",
            "question": "是否继续",
            "question_text": "是否继续",
            "created_at": 1,
        },
    )
    caplog.set_level(logging.INFO)
    assert consume_pending_question("flow:1:s") is None
    assert "event=pending_question_expired" in "\n".join(record.getMessage() for record in caplog.records)
    assert consume_pending_question("") is None


def test_splice_evidence_before_question_text():
    history = [
        HumanMessage(content="查磁盘"),
        AIMessage(content="请选择对象类型\n\n1. 主机\n2. Pod"),
    ]
    evidence = [ToolMessage(content="host", tool_call_id="c1", name="monitor_list_objects")]
    spliced = splice_evidence_messages(history, evidence, "请选择对象类型\n\n1. 主机\n2. Pod")
    assert [type(message).__name__ for message in spliced] == ["HumanMessage", "ToolMessage", "AIMessage"]


def test_answer_after_choice_prompt_detects_numbered_question():
    messages = [
        HumanMessage(content="查 cpu"),
        AIMessage(content="请选择对象类型\n\n1. 主机\n2. Pod"),
        HumanMessage(content="主机"),
    ]
    assert is_answer_after_choice_prompt(messages) is True
    assert is_answer_after_choice_prompt([HumanMessage(content="查 cpu")]) is False


def test_terminal_choice_messages_are_detected():
    from apps.opspilot.utils.pending_question import messages_include_terminal_choice

    assert messages_include_terminal_choice(
        [
            AIMessage(content="", tool_calls=[{"id": "1", "name": "request_user_choice", "args": {}}]),
        ]
    )
    assert messages_include_terminal_choice([AIMessage(content="请选择\n\n1. 主机\n2. Pod")])
    assert not messages_include_terminal_choice([AIMessage(content="CPU 使用率是 12%")])
    assert format_choice_text("继续吗", "confirm", None) == "继续吗\n\n1. 是\n2. 否"
    assert format_choice_text("补充说明", "text", None) == "补充说明"
