"""generation_query_routing_service 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.opspilot.services.wiki.build_service import BuildOutputInvalid
from apps.opspilot.services.wiki.generation_query_routing_service import route_overview_scopes

pytestmark = pytest.mark.unit


def _budget(*, remaining=3):
    return SimpleNamespace(remaining_calls=remaining)


def test_route_overview_scopes_soft_fails_when_llm_empty(monkeypatch):
    """finish_reason=length 导致空输出时，不得抛异常打断 AGUI 主对话。"""

    overview = SimpleNamespace(
        directory_id=11,
        directory=SimpleNamespace(name="运维手册", sort_order=1),
        semantic_status="ready",
        semantic_text="涵盖告警与巡检流程",
        deterministic_text="",
    )
    qs = MagicMock()
    qs.select_related.return_value.order_by.return_value = [overview]
    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_query_routing_service.WikiGenerationOverview.objects.filter",
        lambda **_kwargs: qs,
    )

    def _boom(*_args, **_kwargs):
        raise BuildOutputInvalid(
            "build_output_empty_llm: stage=query_overview_route finish_reason=length " "prompt_tokens=1730 completion_tokens=500"
        )

    kb = SimpleNamespace(pk=7)
    read_scope = SimpleNamespace(generation_id=99)
    result = route_overview_scopes(
        [(kb, read_scope)],
        "如何处理告警",
        llm_model_id=1,
        call_budget=_budget(),
        knowledge_token_limit=6000,
        invoke_llm=_boom,
    )
    assert result.llm_called is True
    assert result.scopes == ()
    assert result.status == "llm_failed"


def test_route_overview_scopes_parses_valid_json(monkeypatch):
    overview = SimpleNamespace(
        directory_id=11,
        directory=SimpleNamespace(name="运维手册", sort_order=1),
        semantic_status="ready",
        semantic_text="涵盖告警与巡检流程",
        deterministic_text="",
    )
    qs = MagicMock()
    qs.select_related.return_value.order_by.return_value = [overview]
    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_query_routing_service.WikiGenerationOverview.objects.filter",
        lambda **_kwargs: qs,
    )

    result = route_overview_scopes(
        [(SimpleNamespace(pk=7), SimpleNamespace(generation_id=99))],
        "如何处理告警",
        llm_model_id=1,
        call_budget=_budget(),
        knowledge_token_limit=6000,
        invoke_llm=lambda *_a, **_k: '{"scopes":[{"kb_id":7,"directory_id":11}]}',
    )
    assert result.status == "routed"
    assert result.scopes == ((7, 11),)
