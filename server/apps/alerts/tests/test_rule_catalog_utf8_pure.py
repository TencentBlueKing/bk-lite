"""规则字段契约是 UTF-8；Windows 默认 GBK 不能作为读取编码。"""

import json
from pathlib import Path

import pytest

from apps.alerts.utils.rule_catalog import FIELDS

pytestmark = pytest.mark.unit

FIELDS_JSON = Path(__file__).resolve().parents[1] / "utils" / "rule_fields.json"
CATALOG = FIELDS_JSON.with_name("rule_catalog.py")


def test_rule_fields_json_is_utf8_not_gbk():
    raw = FIELDS_JSON.read_bytes()
    with pytest.raises(UnicodeDecodeError):
        raw.decode("gbk")
    payload = json.loads(raw.decode("utf-8"))
    assert payload[0]["label"]["zh"] == "标题"


def test_rule_catalog_loads_chinese_labels_and_reads_utf8():
    assert FIELDS["title"]["label"]["zh"] == "标题"
    assert 'read_text(encoding="utf-8")' in CATALOG.read_text(encoding="utf-8")
