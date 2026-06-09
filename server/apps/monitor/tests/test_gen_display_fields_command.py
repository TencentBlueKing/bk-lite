import json

from apps.monitor.management.commands.gen_display_fields import (
    build_display_fields_for_object,
    insert_display_fields_lines,
)


def test_build_display_fields_from_supplementary_indicators():
    obj = {
        "plugin": "Oracle-Exporter",
        "name": "Oracle",
        "supplementary_indicators": ["oracledb_up_gauge", "oracledb_tablespace_used_percent_gauge"],
        "metrics": [
            {"name": "oracledb_up_gauge", "display_name": "OracleDb Status"},
            {"name": "oracledb_tablespace_used_percent_gauge", "display_name": "表空间使用率"},
            {"name": "other", "display_name": "Other"},
        ],
    }
    result = build_display_fields_for_object(obj, plugin_name="Oracle-Exporter")
    assert result == [
        {"name": "OracleDb Status", "sort_order": 0,
         "metrics": [{"plugin": "Oracle-Exporter", "metric": "oracledb_up_gauge"}]},
        {"name": "表空间使用率", "sort_order": 1,
         "metrics": [{"plugin": "Oracle-Exporter", "metric": "oracledb_tablespace_used_percent_gauge"}]},
    ]


def test_build_display_fields_falls_back_to_metric_name_when_no_display_name():
    obj = {
        "supplementary_indicators": ["m1"],
        "metrics": [{"name": "m1"}],  # display_name 缺失
    }
    result = build_display_fields_for_object(obj, plugin_name="P")
    assert result == [{"name": "m1", "sort_order": 0, "metrics": [{"plugin": "P", "metric": "m1"}]}]


def _block(name, plugin, metric):
    return [{"name": name, "sort_order": 0, "metrics": [{"plugin": plugin, "metric": metric}]}]


def test_insert_single_line_array_adds_one_line_after():
    text = (
        '{\n'
        '  "supplementary_indicators": ["cpu"],\n'
        '  "metrics": []\n'
        '}'
    )
    out = insert_display_fields_lines(text, [_block("CPU", "P", "cpu")])
    lines = out.split("\n")
    # 在 supplementary_indicators 行之后、metrics 行之前插入一行，缩进保持 2 空格
    assert lines[1] == '  "supplementary_indicators": ["cpu"],'
    assert lines[2] == '  "display_fields": ' + json.dumps(_block("CPU", "P", "cpu"), ensure_ascii=False) + ','
    assert lines[3] == '  "metrics": []'


def test_insert_multi_line_array_inserts_after_closing_bracket():
    text = (
        '{\n'
        '  "supplementary_indicators": [\n'
        '    "cpu",\n'
        '    "mem"\n'
        '  ],\n'
        '  "metrics": []\n'
        '}'
    )
    out = insert_display_fields_lines(text, [_block("CPU", "P", "cpu")])
    lines = out.split("\n")
    assert lines[4] == '  ],'  # 数组结束行未被破坏
    assert lines[5].strip().startswith('"display_fields":')  # 紧随其后插入
    assert lines[6] == '  "metrics": []'


def test_insert_compound_maps_blocks_in_order():
    text = (
        '{\n'
        '  "objects": [\n'
        '    {\n'
        '      "supplementary_indicators": ["a"],\n'
        '      "metrics": []\n'
        '    },\n'
        '    {\n'
        '      "supplementary_indicators": ["b"],\n'
        '      "metrics": []\n'
        '    }\n'
        '  ]\n'
        '}'
    )
    blocks = [_block("A", "P", "a"), _block("B", "P", "b")]
    out = insert_display_fields_lines(text, blocks)
    assert '"display_fields": ' + json.dumps(_block("A", "P", "a"), ensure_ascii=False) in out
    assert '"display_fields": ' + json.dumps(_block("B", "P", "b"), ensure_ascii=False) in out
    # A 块出现在 B 块之前（顺序映射）
    assert out.index('"metric": "a"') < out.index('"metric": "b"')


def test_insert_skips_empty_block_but_keeps_block_alignment():
    text = (
        '{\n'
        '  "objects": [\n'
        '    {\n'
        '      "supplementary_indicators": [],\n'
        '      "metrics": []\n'
        '    },\n'
        '    {\n'
        '      "supplementary_indicators": ["b"],\n'
        '      "metrics": []\n'
        '    }\n'
        '  ]\n'
        '}'
    )
    blocks = [[], _block("B", "P", "b")]  # 第一个对象无展示列
    out = insert_display_fields_lines(text, blocks)
    assert out.count('"display_fields"') == 1  # 仅第二个对象插入
    assert '"metric": "b"' in out
