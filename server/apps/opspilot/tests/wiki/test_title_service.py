from types import SimpleNamespace


def _kb(rules=None):
    return SimpleNamespace(generation_rules=rules or {})


def test_canonical_title_uses_common_aliases_and_parenthetical_variants():
    from apps.opspilot.services.wiki.title_service import canonical_title, compact_title_key, title_variants

    kb = _kb()

    assert compact_title_key(" CMDB（配置平台） ") == "cmdb配置平台"
    assert title_variants("CMDB（配置平台）") == ["CMDB（配置平台）", "CMDB", "配置平台"]
    assert canonical_title(kb, "CMDB") == "配置平台"
    assert canonical_title(kb, "CMDB（配置平台）") == "配置平台"
    assert canonical_title(kb, "") == ""


def test_generation_rule_aliases_accept_supported_shapes():
    from apps.opspilot.services.wiki.title_service import iter_generation_rule_aliases, title_alias_map

    dict_rules = {"title_aliases": {"数据库": ["DB", "Database"], "应用平台": "APP"}}
    list_rules = {
        "aliases": [
            {"canonical": "消息队列", "aliases": ["MQ", "RabbitMQ"]},
            ["缓存", "Redis", "Cache"],
        ]
    }

    assert list(iter_generation_rule_aliases(dict_rules)) == [
        ("DB", "数据库"),
        ("Database", "数据库"),
        ("应用平台", "APP"),
    ]
    assert list(iter_generation_rule_aliases(list_rules)) == [
        ("MQ", "消息队列"),
        ("RabbitMQ", "消息队列"),
        ("缓存", "缓存"),
        ("Redis", "缓存"),
        ("Cache", "缓存"),
    ]
    assert list(iter_generation_rule_aliases({"title_aliases": "bad"})) == []
    assert title_alias_map(_kb(dict_rules))["database"] == "数据库"


def test_custom_aliases_drive_canonical_title_and_enrichment_terms():
    from apps.opspilot.services.wiki.title_service import canonical_title, title_alias_terms_for_enrichment

    kb = _kb({"titleAliases": [{"canonical": "配置数据库", "aliases": ["CMDB2", "Config DB"]}]})

    assert canonical_title(kb, "Config DB") == "配置数据库"
    assert set(title_alias_terms_for_enrichment(kb, "配置数据库")) == {"配置数据库", "CMDB2", "Config DB"}
    assert {"cmdb", "配置平台"}.issubset(set(title_alias_terms_for_enrichment(_kb(), "配置平台")))
