from types import SimpleNamespace

import pytest

from apps.opspilot.metis.utils.template_loader import TemplateLoader


UNSAFE_DEFAULT_GLOBALS = {"lipsum", "cycler", "joiner", "namespace"}
pytestmark = pytest.mark.integration


def test_template_loader_preserves_repository_template_capabilities(tmp_path):
    template_path = tmp_path / "capabilities.jinja2"
    template_path.write_text(
        "{% set names = [] %}"
        "{% for name, value in fields.items() %}"
        "{% set _ = names.append(name) %}"
        "{{ loop.index|string }}={{ value }};"
        "{% endfor %}"
        "{{ names[0] }}",
        encoding="utf-8",
    )

    rendered = TemplateLoader.render_template(
        "capabilities.jinja2",
        {"fields": {"name": "blueking"}},
        base_path=str(tmp_path),
    )

    assert rendered == "1=blueking;name"


def test_template_loader_environment_has_no_default_globals(tmp_path):
    env = TemplateLoader._get_environment(str(tmp_path))

    assert UNSAFE_DEFAULT_GLOBALS.isdisjoint(env.globals)


def test_all_repository_templates_compile_with_allowlisted_capabilities():
    base_path = TemplateLoader._get_package_support_files_path()
    env = TemplateLoader._get_environment(base_path)
    template_names = env.list_templates()

    assert template_names
    for template_name in template_names:
        env.get_template(template_name)


def test_naive_rag_prompt_renders_and_deduplicates_knowledge_sources():
    rag_results = [
        SimpleNamespace(
            title="",
            knowledge_id=7,
            chunk_number=index,
            chunk_id=f"chunk-{index}",
            segment_number=index,
            segment_id=f"segment-{index}",
            content=f"content-{index}",
            chunk_type="Document",
        )
        for index in (1, 2)
    ]

    rendered = TemplateLoader.render_template(
        "graph/naive_rag_node_prompt.jinja2",
        {
            "rag_results": rag_results,
            "enable_rag_source": True,
            "enable_rag_strict_mode": False,
        },
    )
    source_summary = rendered.split("### 引用资料汇总", 1)[1].split("请在回答中适当引用这些资料。", 1)[0]

    assert "知识片段1" in rendered
    assert source_summary.count("(knowledge_id: 7)") == 1
