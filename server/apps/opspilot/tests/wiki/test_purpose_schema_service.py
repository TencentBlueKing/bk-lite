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
