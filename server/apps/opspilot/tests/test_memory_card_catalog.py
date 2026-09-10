"""记忆卡片目录：按 ### 标题拆分、按键匹配、写回单卡。"""

from apps.opspilot.services.memory_card_catalog import (
    append_card,
    extract_card_keys,
    match_card_by_keys,
    parse_memory_cards,
    replace_card,
    resolve_catalog_match,
    split_incoming_units,
    truncate_classify_content,
)


class TestParseMemoryCards:
    def test_无三级标题视为无卡片(self):
        assert parse_memory_cards("旧内容\n\n第二段") == []

    def test_按三级标题拆成卡片并保留前置章节(self):
        content = (
            "## 数据缺口\n\n" "### Unhealthy\n" "- reason: Unhealthy\n" "- 复发: 2026-08-06 20:03 | web | unknown\n\n" "### BackOff\n" "- reason: BackOff\n"
        )
        cards = parse_memory_cards(content)
        assert [card.heading for card in cards] == ["Unhealthy", "BackOff"]
        assert "reason: Unhealthy" in cards[0].body
        assert "### BackOff" not in cards[0].body
        assert content[cards[0].start : cards[0].end] == cards[0].body
        rebuilt = content[: cards[0].start] + cards[0].body + content[cards[0].end :]
        assert rebuilt == content


class TestExtractAndMatchKeys:
    def test_抽取标题_reason_和root_cause_id(self):
        text = "### RC-JVM-CGROUP-001\n- reason: OOMKilled\n- root_cause_id: RC-JVM-CGROUP-001\n"
        keys = extract_card_keys(text)
        assert "RC-JVM-CGROUP-001" in keys
        assert "OOMKilled" in keys

    def test_键相等命中忽略大小写和空白(self):
        cards = parse_memory_cards("### Unhealthy\n- reason: Unhealthy\n\n### BackOff\n- reason: BackOff\n")
        hit = match_card_by_keys(cards, {"  unhealthy "})
        assert hit is not None
        assert hit.heading == "Unhealthy"

    def test_键不相等不命中(self):
        cards = parse_memory_cards("### Unhealthy\n- reason: Unhealthy\n")
        assert match_card_by_keys(cards, {"Readiness probe failed"}) is None

    def test_优先命中标题完全一致的卡片(self):
        cards = parse_memory_cards("### Unhealthy\n- reason: FailedReady\n\n### FailedReady\n- reason: FailedReady\n")
        hit = match_card_by_keys(cards, {"FailedReady"})
        assert hit is not None
        assert hit.heading == "FailedReady"


class TestIncomingUnitsAndPatch:
    def test_新内容多张卡片拆成多条(self):
        units = split_incoming_units("### A\n- reason: A\n\n### B\n- reason: B\n")
        assert len(units) == 2
        assert units[0].startswith("### A")
        assert units[1].startswith("### B")

    def test_无三级标题整段作为一条(self):
        assert split_incoming_units("Readiness probe failed") == ["Readiness probe failed"]

    def test_替换命中卡片其它卡片保持原样(self):
        content = "### Unhealthy\n- reason: Unhealthy\n\n### BackOff\n- reason: BackOff\n"
        cards = parse_memory_cards(content)
        updated = replace_card(content, cards[0], "### Unhealthy\n- reason: Unhealthy\n- 复发: 2026-09-09 11:00 | web | INC-1")
        assert "### BackOff" in updated
        assert "- reason: BackOff" in updated
        assert "INC-1" in updated
        assert updated.count("### Unhealthy") == 1

    def test_追加新卡片到文末(self):
        content = "### Unhealthy\n- reason: Unhealthy\n"
        updated = append_card(content, "### ImagePullBackOff\n- reason: ImagePullBackOff\n")
        assert updated.startswith("### Unhealthy")
        assert updated.strip().endswith("- reason: ImagePullBackOff")

    def test_目录匹配按index或heading解析(self):
        cards = parse_memory_cards("### Unhealthy\n- reason: Unhealthy\n\n### BackOff\n- reason: BackOff\n")
        assert resolve_catalog_match(cards, {"action": "update", "index": 1}).heading == "BackOff"
        assert resolve_catalog_match(cards, {"action": "update", "heading": "unhealthy"}).heading == "Unhealthy"
        assert resolve_catalog_match(cards, {"action": "create"}) is None
        assert resolve_catalog_match(cards, {"action": "update", "index": 9}) is None

    def test_分类材料截断新内容(self):
        assert "已截断" in truncate_classify_content("x" * 5000)
        assert truncate_classify_content("short") == "short"
