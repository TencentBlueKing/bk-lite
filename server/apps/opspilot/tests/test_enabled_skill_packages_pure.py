"""enabled_skill_packages 通路单元测试(viewset 层,纯函数)。

验证:
  - 用户显式选中的 skill_packages 集合会原样写入 params["enabled_skill_packages"]
  - 与 params["matched_skill_packages"] (top-3 by score) 独立存在
  - 即使 substring 匹配 score=0,enabled 仍保留全集
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.opspilot.viewsets.llm_view import LLMViewSet

pytestmark = pytest.mark.unit


def test_apply_skill_packages_writes_both_matched_and_enabled():
    """_apply_skill_packages_to_params 同时写 matched(走匹配)和 enabled(全集)。"""
    # mock hydrate 原样返回,确保不被 DB 影响
    with patch("apps.opspilot.viewsets.llm_view.hydrate_skill_packages", side_effect=lambda pkgs: pkgs):
        viewset = LLMViewSet()
        skill = SimpleNamespace(
            skill_prompt="你是助手。",
            skill_packages=[
                {
                    "id": 1,
                    "name": "PDF Reader",
                    "description": "Extract text from PDFs.",
                    "required_tools": ["pdftotext"],
                    "triggers": ["pdf"],
                    "skill_markdown": "Use pdftotext.",
                },
                {
                    "id": 2,
                    "name": "Kubernetes Specialist",
                    "description": "Diagnose k8s workloads.",
                    "required_tools": ["kubernetes"],
                    "triggers": ["k8s"],
                    "skill_markdown": "Run kubectl.",
                },
            ],
        )
        params = {
            "skill_prompt": "你是助手。",
            # 用户消息不含任何 trigger / description 关键词 → score=0 → matched 为空
            "user_message": "你好",
            "tools": [{"name": "kubernetes"}],
        }
        viewset._apply_skill_packages_to_params(params, skill)

    # matched 是 top-3 by score,本场景 score=0 → 空
    assert params["matched_skill_packages"] == []
    # enabled 始终是全集,与 substring 匹配无关
    assert len(params["enabled_skill_packages"]) == 2
    enabled_ids = {p["id"] for p in params["enabled_skill_packages"]}
    assert enabled_ids == {1, 2}


def test_apply_skill_packages_enabled_independent_of_match_score():
    """用户消息含触发词 → matched 非空,但 enabled 仍是全集(不缩水)。

    注意:id 字段在 matched(经 build_skill_package_prompt 转换)中是 str,
    在 enabled(直接用 skill_packages)中保留原 int。测试按各自类型断言。
    """
    with patch("apps.opspilot.viewsets.llm_view.hydrate_skill_packages", side_effect=lambda pkgs: pkgs):
        viewset = LLMViewSet()
        skill = SimpleNamespace(
            skill_prompt="",
            skill_packages=[
                {"id": 1, "name": "PDF Reader", "description": "Extract PDF text.", "required_tools": [], "triggers": ["pdf"], "skill_markdown": ""},
                {"id": 2, "name": "Markitdown", "description": "Convert files to markdown.", "required_tools": [], "triggers": ["pdf"], "skill_markdown": ""},
                {"id": 3, "name": "Kubernetes Specialist", "description": "k8s.", "required_tools": [], "triggers": ["k8s"], "skill_markdown": ""},
                {"id": 4, "name": "XGet", "description": "fetch urls.", "required_tools": [], "triggers": ["xget"], "skill_markdown": ""},
            ],
        )
        params = {
            "skill_prompt": "",
            "user_message": "把这个 PDF 转一下",  # 命中 1, 2 (triggers="pdf")
            "tools": [],
        }
        viewset._apply_skill_packages_to_params(params, skill)

    # matched 经 build_skill_package_prompt 转换:id 转 str
    matched_ids = {p["id"] for p in params["matched_skill_packages"]}
    assert matched_ids == {"1", "2"}  # top-3 by score(实际只 2 个命中)

    # enabled = skill_packages 原样:id 保持原 int
    enabled_ids = {p["id"] for p in params["enabled_skill_packages"]}
    assert enabled_ids == {1, 2, 3, 4}  # 全集,与匹配无关


def test_apply_skill_packages_enabled_empty_when_no_selection():
    """skill_packages 为空时,enabled 也为空。"""
    with patch("apps.opspilot.viewsets.llm_view.hydrate_skill_packages", side_effect=lambda pkgs: pkgs):
        viewset = LLMViewSet()
        skill = SimpleNamespace(skill_prompt="", skill_packages=[])
        params = {"skill_prompt": "", "user_message": "你好", "tools": []}
        viewset._apply_skill_packages_to_params(params, skill)

    assert params["enabled_skill_packages"] == []
    assert params["matched_skill_packages"] == []
