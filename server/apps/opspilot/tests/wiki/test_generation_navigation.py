"""generation_navigation_service 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.opspilot.services.wiki.build_service import BuildOutputInvalid
from apps.opspilot.services.wiki.generation_navigation_service import enhance_generation_overviews

pytestmark = pytest.mark.unit


def _budget(*, remaining=3, remaining_soft_tokens=20000):
    return SimpleNamespace(
        remaining_calls=remaining,
        remaining_soft_tokens=remaining_soft_tokens,
        max_context_tokens_per_call=None,
    )


def _patch_generation(monkeypatch, overview):
    generation = MagicMock()
    generation.overviews.order_by.return_value = [overview]
    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_navigation_service.WikiGeneration.objects.get",
        lambda pk: generation,
    )
    return generation


def test_enhance_generation_overviews_soft_fails_when_llm_truncated_empty(monkeypatch, caplog):
    """finish_reason=length 空输出不得打断资料构建激活。"""

    overview = SimpleNamespace(
        id=1,
        directory_id=None,
        scope_key="__root__",
        deterministic_text="告警处理流程见页面 [1]。",
        referenced_page_ids=[1],
    )
    generation = _patch_generation(monkeypatch, overview)

    def _boom(*_args, **_kwargs):
        raise BuildOutputInvalid(
            "build_output_empty_llm: stage=material_semantic_overview finish_reason=length " "prompt_tokens=795 completion_tokens=2000"
        )

    with caplog.at_level("WARNING"):
        result = enhance_generation_overviews(
            99,
            llm_model_id=1,
            budget=_budget(),
            invoke_llm=_boom,
        )

    assert result["status"] == "llm_failed"
    assert result["llm_called"] is True
    assert result["updated"] == 0
    generation.overviews.update.assert_called_once_with(semantic_status="skipped", semantic_text="")
    assert "wiki semantic overview LLM 失败" in caplog.text
    assert "generation_id=99" in caplog.text
    assert "error_type=BuildOutputInvalid" in caplog.text
