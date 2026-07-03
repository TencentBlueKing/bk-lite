from types import SimpleNamespace
from unittest.mock import patch


def test_templates_listed():
    from apps.opspilot.services.wiki.purpose_schema_service import list_templates

    keys = {t["key"] for t in list_templates()}
    assert {"ops_qa", "fault_diagnosis", "operation_guide", "product_support", "general"} <= keys


def test_generate_purpose_schema_uses_llm():
    from apps.opspilot.services.wiki.purpose_schema_service import generate_purpose_schema

    with patch(
        "apps.opspilot.services.wiki.purpose_schema_service._llm_generate",
        return_value=("# Purpose\nX", "# Schema\nY"),
    ):
        purpose, schema = generate_purpose_schema(template_key="ops_qa", description="运维问答库", llm_model_id=42)
    assert purpose.startswith("# Purpose") and schema.startswith("# Schema")


def test_generate_purpose_schema_fallback_without_model():
    from apps.opspilot.services.wiki.purpose_schema_service import generate_purpose_schema

    purpose, schema = generate_purpose_schema(template_key="ops_qa", description="运维问答库", llm_model_id=None)
    assert "运维问答库" in purpose  # 描述注入到 Purpose 骨架
    assert "知识类型" in schema  # 模板 Schema 骨架


def test_parse_llm_output_requires_markers():
    from apps.opspilot.services.wiki import purpose_schema_service as service

    purpose, schema = service._parse_llm_output("===PURPOSE===\n# P\n===SCHEMA===\n# S")
    assert purpose == "# P"
    assert schema == "# S"

    try:
        service._parse_llm_output("# P\n# S")
    except ValueError as exc:
        assert "PURPOSE/SCHEMA" in str(exc)
    else:
        raise AssertionError("invalid output should raise")


def test_llm_generate_invokes_model_and_parses_output(monkeypatch):
    from apps.opspilot.services.wiki import purpose_schema_service as service

    prompts = []
    monkeypatch.setattr(
        service.LLMModel.objects,
        "get",
        lambda id: SimpleNamespace(openai_api_base="http://llm", openai_api_key="key", model_name="model"),
    )

    def fake_invoke(request, messages):
        prompts.append(messages[0]["content"])
        return "===PURPOSE===\n# Generated Purpose\n===SCHEMA===\n# Generated Schema"

    monkeypatch.setattr(service.LLMClientFactory, "invoke_isolated", fake_invoke)

    template = {"purpose_md": "# Purpose\n{{description}}", "schema_md": "# Schema\n- concept"}
    purpose, schema = service._llm_generate(template, "蓝鲸平台知识库", llm_model_id=1)

    assert purpose == "# Generated Purpose"
    assert schema == "# Generated Schema"
    assert "蓝鲸平台知识库" in prompts[0]


def test_llm_generate_falls_back_when_llm_output_invalid(monkeypatch):
    from apps.opspilot.services.wiki import purpose_schema_service as service

    monkeypatch.setattr(
        service.LLMModel.objects,
        "get",
        lambda id: SimpleNamespace(openai_api_base="http://llm", openai_api_key="key", model_name="model"),
    )
    monkeypatch.setattr(service.LLMClientFactory, "invoke_isolated", lambda request, messages: "invalid")

    template = {"purpose_md": "# Purpose\n{{description}}", "schema_md": "# Schema\n- concept"}
    purpose, schema = service._llm_generate(template, "回退描述", llm_model_id=1)

    assert "回退描述" in purpose
    assert schema == "# Schema\n- concept"
