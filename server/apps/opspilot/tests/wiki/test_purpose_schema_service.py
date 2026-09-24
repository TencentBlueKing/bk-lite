from apps.opspilot.services.wiki.purpose_schema_service import (
    FROZEN_PAGE_TYPES,
    MATERIALS_ROOT_IMPORT_NAME,
    MATERIALS_ROOT_KEY,
    get_frozen_structure,
    get_template_structure,
    import_folder_display_name,
    is_materials_root_name,
    match_frozen_knowledge_root_name,
)


def test_frozen_structure_has_five_page_types_and_six_roots():
    structure = get_frozen_structure()
    assert structure["page_types"] == list(FROZEN_PAGE_TYPES)
    names = [item["name"] for item in structure["directories"]]
    assert names == ["实体", "概念", "待研究问题", "对比", "综合", "来源"]
    source = next(item for item in structure["directories"] if item["key"] == MATERIALS_ROOT_KEY)
    assert source["accepts_pages"] is False
    assert source["rules"]["allowed_page_types"] == []
    assert "source" not in structure["page_types"]


def test_any_template_key_returns_frozen_structure():
    general = get_template_structure("general")
    unknown = get_template_structure("ops_qa")
    assert general["page_types"] == unknown["page_types"]
    assert [item["key"] for item in general["directories"]] == [item["key"] for item in unknown["directories"]]


def test_display_name_match_ignores_english_type_keys():
    assert match_frozen_knowledge_root_name("实体")["key"] == "schema_entity"
    assert match_frozen_knowledge_root_name(" 实体 ")["key"] == "schema_entity"
    assert match_frozen_knowledge_root_name("entity") is None
    assert match_frozen_knowledge_root_name("来源") is None
    assert is_materials_root_name("来源") is True
    assert is_materials_root_name("sources") is False
    assert import_folder_display_name("来源", parent_is_root=True) == MATERIALS_ROOT_IMPORT_NAME
    assert import_folder_display_name("来源", parent_is_root=False) == "来源"
    assert import_folder_display_name("entity", parent_is_root=True) == "entity"
