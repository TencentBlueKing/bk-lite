"""chat_service._maybe_save_answer_as_wiki_candidate 单元测试。

覆盖:
- 未配置 wiki_save_answer_as_candidate:不保存
- chat 失败:不落候选
- 没有 wiki_kb_ids:不落候选
- doc_map 没有 wiki 来源:不落候选
- 全部条件满足:直接准入 active KnowledgePage,不创建第三类审批
- 自动保存异常被吞掉(不阻塞 chat 主流程)
"""

from types import SimpleNamespace
from unittest.mock import patch

from apps.opspilot.services import chat_service


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def test_no_flag_skips_save():
    """未配置 wiki_save_answer_as_candidate:不落候选。"""
    kwargs = {"wiki_kb_ids": [1]}
    chat_result = {"message": "回答内容", "success": True}
    doc_map = {"doc1": {"source": "wiki", "title": "page"}}
    assert chat_service._maybe_save_answer_as_wiki_candidate(kwargs, chat_result, doc_map) is None


def test_chat_failed_skips_save():
    """chat 失败:不落候选。"""
    kwargs = {"wiki_save_answer_as_candidate": True, "wiki_kb_ids": [1]}
    chat_result = {"message": "", "success": False}
    doc_map = {"doc1": {"source": "wiki"}}
    assert chat_service._maybe_save_answer_as_wiki_candidate(kwargs, chat_result, doc_map) is None


def test_no_wiki_kb_ids_skips_save():
    """没有 wiki_kb_ids:不落候选。"""
    kwargs = {"wiki_save_answer_as_candidate": True, "wiki_kb_ids": []}
    chat_result = {"message": "回答", "success": True}
    doc_map = {"doc1": {"source": "wiki"}}
    assert chat_service._maybe_save_answer_as_wiki_candidate(kwargs, chat_result, doc_map) is None


def test_no_wiki_doc_in_doc_map_skips_save():
    """doc_map 没有 wiki 来源:不落候选(避免把非 wiki 回答存到 wiki)。"""
    kwargs = {"wiki_save_answer_as_candidate": True, "wiki_kb_ids": [1]}
    chat_result = {"message": "回答", "success": True}
    doc_map = {"doc1": {"source": "skill"}}
    assert chat_service._maybe_save_answer_as_wiki_candidate(kwargs, chat_result, doc_map) is None


def test_doc_map_not_dict_skips_save():
    """doc_map 非 dict:不落候选。"""
    kwargs = {"wiki_save_answer_as_candidate": True, "wiki_kb_ids": [1]}
    chat_result = {"message": "回答", "success": True}
    assert chat_service._maybe_save_answer_as_wiki_candidate(kwargs, chat_result, None) is None


def test_empty_body_skips_save():
    """body 为空:不自动保存(避免空页)。"""
    with (
        patch("apps.opspilot.models.WikiKnowledgeBase.objects") as kb_mgr,
        patch("apps.opspilot.services.wiki.page_service.save_answer_page") as save_fn,
    ):
        kb_mgr.filter.return_value.first.return_value = SimpleNamespace(id=1)
        kwargs = {"wiki_save_answer_as_candidate": True, "wiki_kb_ids": [1]}
        chat_result = {"message": "   ", "success": True}
        doc_map = {"doc1": {"source": "wiki"}}
        result = chat_service._maybe_save_answer_as_wiki_candidate(kwargs, chat_result, doc_map)
    assert result is None
    save_fn.assert_not_called()


def test_happy_path_directly_admits_page_without_approval():
    """全部条件满足时直接准入 active KnowledgePage,不产生 qa_answer_candidate。
    保留旧配置键仅用于调用兼容,保存行为不再进入人工审批。
    """
    page_mock = SimpleNamespace(id=42, status="active", knowledge_base_id=1, title="CMDB 是什么", contribution="mixed", update_method="qa_answer")
    with (
        patch("apps.opspilot.models.WikiKnowledgeBase.objects") as kb_mgr,
        patch("apps.opspilot.services.wiki.page_service.save_answer_page", return_value=page_mock) as save_fn,
        patch("apps.opspilot.services.wiki.cascade_service.cascade") as cascade_fn,
    ):
        kb_mgr.filter.return_value.first.return_value = SimpleNamespace(id=1)
        kwargs = {
            "wiki_save_answer_as_candidate": True,
            "wiki_kb_ids": [1],
            "chat_id": "chat-123",
            "message_id": "msg-456",
            "user": "alice",
        }
        chat_result = {"message": "CMDB 是什么\n\n是蓝鲸的配置平台", "success": True}
        doc_map = {"doc1": {"source": "wiki", "title": "CMDB"}}

        page = chat_service._maybe_save_answer_as_wiki_candidate(kwargs, chat_result, doc_map)

    assert page is not None
    assert page.id == 42
    # 验证回答直接通过 save_answer_page 准入
    save_fn.assert_called_once()
    call_kwargs = save_fn.call_args.kwargs
    assert call_kwargs["knowledge_base"].id == 1
    assert call_kwargs["page_type"] == "qa"
    assert call_kwargs["title"].startswith("CMDB")
    assert "CMDB" in call_kwargs["body"]
    assert call_kwargs["source_conversation_id"] == "chat-123"
    assert call_kwargs["source_message_id"] == "msg-456"
    assert call_kwargs["source_channel"] == "chat_service"
    assert call_kwargs["created_by"] == "alice"
    cascade_fn.assert_called_once_with(call_kwargs["knowledge_base"], [page.id], "qa_answer_save")


def test_exception_does_not_break_chat():
    """自动保存异常时不应抛错(不阻塞 chat 主流程)。"""
    with (
        patch("apps.opspilot.models.WikiKnowledgeBase.objects") as kb_mgr,
        patch(
            "apps.opspilot.services.wiki.page_service.save_answer_page",
            side_effect=RuntimeError("disk full"),
        ),
    ):
        kb_mgr.filter.return_value.first.return_value = SimpleNamespace(id=1)
        kwargs = {"wiki_save_answer_as_candidate": True, "wiki_kb_ids": [1]}
        chat_result = {"message": "回答", "success": True}
        doc_map = {"doc1": {"source": "wiki"}}

        result = chat_service._maybe_save_answer_as_wiki_candidate(kwargs, chat_result, doc_map)
    assert result is None


def test_custom_wiki_doc_marker():
    """wiki_doc_marker 可定制:用于不同业务来源标识。"""
    page_mock = SimpleNamespace(id=7, status="active")
    with (
        patch("apps.opspilot.models.WikiKnowledgeBase.objects") as kb_mgr,
        patch("apps.opspilot.services.wiki.page_service.save_answer_page", return_value=page_mock),
        patch("apps.opspilot.services.wiki.cascade_service.cascade"),
    ):
        kb_mgr.filter.return_value.first.return_value = SimpleNamespace(id=1)
        kwargs = {
            "wiki_save_answer_as_candidate": True,
            "wiki_kb_ids": [1],
            "wiki_doc_marker": "ops_wiki",
        }
        chat_result = {"message": "回答", "success": True}
        doc_map = {"doc1": {"source": "ops_wiki", "title": "x"}}

        page = chat_service._maybe_save_answer_as_wiki_candidate(kwargs, chat_result, doc_map)
    assert page is not None
    assert page.id == 7
