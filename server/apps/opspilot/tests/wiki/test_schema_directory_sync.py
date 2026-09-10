import pytest

from apps.opspilot.models import WikiDirectory
from apps.opspilot.services.wiki.purpose_schema_service import list_templates
from apps.opspilot.services.wiki.schema_directory_sync_service import apply_schema_markdown_structure, parse_schema_markdown
from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base


def test_parse_hermes_prose_nests_ascii_folders_under_wiki():
    parsed = parse_schema_markdown(
        """压缩包去掉仓库根后第一层为 `wiki/`。

- `architecture`：运行架构与数据流
- `operations`：部署、升级、容量、排障、验收（`concept`）
"""
    )
    parts = {item["parts"] for item in parsed["paths"]}
    assert ("wiki", "architecture") in parts
    assert ("wiki", "operations") in parts


_NESTED_WIKI_SCHEMA_MD = """压缩包去掉仓库根后第一层为 `wiki/`。

- `wiki/architecture`：运行架构与数据流（`concept`）
- `wiki/operations`：部署、升级、容量、排障、验收（`concept`）
- `wiki/product`：产品矩阵、文档与交付导航（`entity`）
"""


def test_parse_okf_schema_markdown_reads_nested_paths():
    parsed = parse_schema_markdown(_NESTED_WIKI_SCHEMA_MD)
    parts = {item["parts"] for item in parsed["paths"]}
    assert ("wiki", "operations") in parts
    assert ("wiki", "product") in parts
    assert ("实体",) not in parts
    types = {item.casefold() for item in parsed["page_types"]}
    assert {"entity", "concept"} <= types
    product = next(item for item in parsed["paths"] if item["parts"] == ("wiki", "product"))
    assert product["page_type"].casefold() == "entity"


def test_parse_general_schema_markdown_uses_type_display_names():
    schema_md = next(item["schema_md"] for item in list_templates() if item["key"] == "general")
    parsed = parse_schema_markdown(schema_md)
    names = {item["parts"][0] for item in parsed["paths"]}
    assert names == {"实体", "概念", "来源", "待研究问题", "对比", "综合"}


@pytest.mark.django_db(transaction=True)
def test_apply_okf_schema_replaces_general_directories(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base(template_key="general")
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    apply_schema_markdown_structure(knowledge_base, _NESTED_WIKI_SCHEMA_MD, operator="admin")
    wiki = WikiDirectory.objects.get(knowledge_base=knowledge_base, name="wiki", status="active")
    operations = WikiDirectory.objects.get(
        knowledge_base=knowledge_base,
        name="operations",
        status="active",
    )
    assert operations.parent_id == wiki.pk
    assert not WikiDirectory.objects.filter(
        knowledge_base=knowledge_base,
        name="实体",
        status="active",
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_apply_already_stored_hermes_schema_replaces_general_directories(wiki_factory):
    schema_md = """压缩包去掉仓库根后第一层为 `wiki/`。

- `architecture`：运行架构与数据流
- `operations`：部署（`concept`）
"""
    knowledge_base = wiki_factory.knowledge_base(template_key="general", schema_md=schema_md)
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    apply_schema_markdown_structure(knowledge_base, knowledge_base.schema_md, operator="admin")
    wiki = WikiDirectory.objects.get(knowledge_base=knowledge_base, name="wiki", status="active")
    architecture = WikiDirectory.objects.get(
        knowledge_base=knowledge_base,
        name="architecture",
        status="active",
    )
    assert architecture.parent_id == wiki.pk
    assert not WikiDirectory.objects.filter(
        knowledge_base=knowledge_base,
        name="实体",
        status="active",
    ).exists()
