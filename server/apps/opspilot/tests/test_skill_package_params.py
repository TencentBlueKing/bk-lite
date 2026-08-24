"""技能包执行期参数：掩码往返、校验、缺必填标注。"""

from types import SimpleNamespace

import pytest

from apps.core.mixinx import EncryptMixin
from apps.opspilot.serializers.llm_serializer import LLMSerializer
from apps.opspilot.utils.prompt_utils import MASK_VALUE
from apps.opspilot.utils.skill_package_params import (
    MAX_VARS_PER_PACKAGE,
    annotate_packages_missing_params,
    decrypt_package_params,
    format_skillenv,
    list_missing_required_params,
    mask_package_params,
    merge_package_params,
    validate_package_params,
)

pytestmark = pytest.mark.unit


def _encrypt(value: str) -> str:
    row = {"value": value}
    EncryptMixin.encrypt_field("value", row)
    return row["value"]


def test_skill_package_serializer_exposes_variables():
    from apps.opspilot.serializers.llm_serializer import SkillPackageSerializer

    assert "variables" in SkillPackageSerializer.Meta.fields
    assert hasattr(SkillPackageSerializer, "get_variables")


def test_get_variables_reads_manifest_and_overlay(tmp_path):
    from apps.opspilot.serializers.llm_serializer import SkillPackageSerializer

    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "skill.yaml").write_text(
        "id: demo\nvariables:\n  - name: DEMO_HOST\n    required: true\n    type: text\n",
        encoding="utf-8",
    )
    instance = SimpleNamespace(
        manifest={"variables": [{"name": "LEGACY", "required": False}]},
        storage_path=str(tmp_path),
    )
    assert SkillPackageSerializer.get_variables(instance) == [{"name": "DEMO_HOST", "required": True, "type": "text"}]


def test_mask_package_params_masks_password_only():
    raw = {
        "ad-toolkit": [
            {"key": "AD_SERVER", "value": "ldaps://dc", "type": "text"},
            {"key": "AD_PASSWORD", "value": "cipher", "type": "password"},
            {"key": "AD_CERT", "value": "-----BEGIN CERT-----", "type": "textarea"},
        ]
    }
    masked = mask_package_params(raw)
    assert masked["ad-toolkit"][0]["value"] == "ldaps://dc"
    assert masked["ad-toolkit"][1]["value"] == MASK_VALUE
    assert masked["ad-toolkit"][2]["value"] == "-----BEGIN CERT-----"
    assert raw["ad-toolkit"][1]["value"] == "cipher"


def test_get_skill_package_params_masks_and_handles_none():
    instance = SimpleNamespace(
        skill_package_params={
            "ad-toolkit": [{"key": "TOKEN", "type": "password", "value": "super-secret"}],
        }
    )
    result = LLMSerializer.get_skill_package_params(instance)
    assert result["ad-toolkit"][0]["value"] == MASK_VALUE
    assert instance.skill_package_params["ad-toolkit"][0]["value"] == "super-secret"
    assert LLMSerializer.get_skill_package_params(SimpleNamespace(skill_package_params=None)) == {}


def test_merge_package_params_restores_mask_and_encrypts_plaintext():
    stored = {
        "ad-toolkit": [{"key": "AD_PASSWORD", "value": _encrypt("old-secret"), "type": "password", "multiline": False}],
    }
    incoming = {
        "ad-toolkit": [
            {"key": "AD_PASSWORD", "value": MASK_VALUE, "type": "password"},
            {"key": "AD_TOKEN", "value": "new-secret", "type": "password"},
        ]
    }
    merged = merge_package_params(incoming, stored)
    assert merged["ad-toolkit"][0]["value"] == stored["ad-toolkit"][0]["value"]
    assert merged["ad-toolkit"][1]["value"] != "new-secret"
    plain, secrets = decrypt_package_params(merged)
    assert plain["ad-toolkit"]["AD_PASSWORD"] == "old-secret"
    assert plain["ad-toolkit"]["AD_TOKEN"] == "new-secret"
    assert secrets["ad-toolkit"] == {"AD_PASSWORD", "AD_TOKEN"}


def test_merge_package_params_none_keeps_stored():
    stored = {"ad-toolkit": [{"key": "A", "value": "1", "type": "text"}]}
    assert merge_package_params(None, stored) == stored
    assert merge_package_params({}, stored) == {}


def test_validate_package_params_rejects_bad_name_duplicate_and_limits():
    with pytest.raises(ValueError, match="变量名不合法"):
        validate_package_params({"pkg": [{"key": "1BAD", "value": "x", "type": "text"}]})
    with pytest.raises(ValueError, match="重复变量名"):
        validate_package_params(
            {
                "pkg": [
                    {"key": "TOKEN", "value": "a", "type": "text"},
                    {"key": "TOKEN", "value": "b", "type": "text"},
                ]
            }
        )
    with pytest.raises(ValueError, match="变量数不能超过"):
        validate_package_params({"pkg": [{"key": f"K{i}", "value": "x", "type": "text"} for i in range(MAX_VARS_PER_PACKAGE + 1)]})
    with pytest.raises(ValueError, match="超过"):
        validate_package_params({"pkg": [{"key": "BIG", "value": "x" * (64 * 1024 + 1), "type": "text"}]})


def test_validate_package_params_accepts_underscore_names():
    out = validate_package_params({"pkg": [{"key": "_PRIVATE", "value": "ok", "type": "text"}]})
    assert out["pkg"][0]["key"] == "_PRIVATE"


def test_validate_package_params_accepts_textarea_and_coerces_multiline():
    out = validate_package_params(
        {
            "pkg": [
                {"key": "CERT", "value": "a\nb", "type": "textarea"},
                {"key": "NOTE", "value": "x", "type": "text", "multiline": True},
            ]
        }
    )
    assert out["pkg"][0]["type"] == "textarea"
    assert out["pkg"][0]["multiline"] is True
    assert out["pkg"][1]["type"] == "textarea"


def test_list_missing_required_params_and_prompt_annotation():
    package = {
        "package_id": "ad-toolkit",
        "name": "AD 工具",
        "variables": [
            {"name": "AD_SERVER", "required": True},
            {"name": "AD_PASSWORD", "required": True},
            {"name": "AD_NOTE", "required": False},
        ],
    }
    missing = list_missing_required_params(package, [{"key": "AD_SERVER", "value": "dc"}])
    assert missing == ["AD_PASSWORD"]

    annotated = annotate_packages_missing_params([package], {"ad-toolkit": [{"key": "AD_SERVER", "value": "dc"}]})
    assert annotated[0]["missing_params"] == ["AD_PASSWORD"]

    from apps.opspilot.services.skill_package.runtime import append_matching_skill_packages_to_prompt

    prompt = append_matching_skill_packages_to_prompt(
        base_prompt="你是运维助手。",
        skill_packages=annotated,
        user_message="域账号",
        available_tool_names=set(),
    )
    assert "缺少必填变量：AD_PASSWORD，本包不可用" in prompt


def test_format_skillenv_quotes_and_escapes():
    text = format_skillenv({"SIMPLE": "ok", "SPACE": "a b", "MULTI": "a\nb"})
    assert "SIMPLE=ok\n" in text
    assert 'SPACE="a b"' in text
    assert "MULTI=a\\nb" in text


def test_map_params_to_skill_dirs_uses_package_id():
    from apps.opspilot.utils.skill_package_params import map_params_to_skill_dirs

    by_dir, secrets = map_params_to_skill_dirs(
        [{"package_id": "ad-domain-ops", "name": "AD 域运维"}],
        {"ad-domain-ops": {"AD_HOST": "10.0.0.1", "AD_BIND_PASSWORD": "secret"}},
        {"ad-domain-ops": {"AD_BIND_PASSWORD"}},
    )
    assert by_dir["ad-domain-ops"]["AD_HOST"] == "10.0.0.1"
    assert secrets == ["secret"]


def test_resolve_package_params_empty_overlay_falls_back_to_db(monkeypatch):
    from apps.opspilot.utils import skill_package_params as mod

    monkeypatch.setattr(
        mod,
        "_load_stored_params",
        lambda skill_id: {"ad-domain-ops": [{"key": "AD_HOST", "value": "dc.example", "type": "text"}]},
    )
    plain, _secrets = mod.resolve_package_params(29, overlay={})
    assert plain["ad-domain-ops"]["AD_HOST"] == "dc.example"


def test_tools_nodes_loads_runtime_params_from_overlay():
    from apps.opspilot.metis.llm.chain.node import ToolsNodes

    request = SimpleNamespace(
        extra_config={
            "skill_id": 29,
            "skill_package_params_overlay": {
                "ad-domain-ops": [
                    {"key": "AD_HOST", "value": "10.10.248.33", "type": "text"},
                    {"key": "AD_BIND_DN", "value": "cn=admin", "type": "text"},
                ]
            },
        }
    )
    by_dir, _secrets = ToolsNodes._load_skill_package_runtime_params(
        request,
        [{"package_id": "ad-domain-ops", "name": "AD 域运维"}],
    )
    assert by_dir["ad-domain-ops"]["AD_HOST"] == "10.10.248.33"
    assert by_dir["ad-domain-ops"]["AD_BIND_DN"] == "cn=admin"
