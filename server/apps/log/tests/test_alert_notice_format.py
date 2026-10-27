"""命中行：有 conditions 时逐条渲染，没有时保持第一批格式。"""

from apps.log.services.alert_notice_format import format_hit_line


def test_old_aggregate_result_keeps_first_batch_hit_line():
    text = format_hit_line({"count": 180, "count_rate": 0.6, "count_delta": 130})
    assert text == "命中条数：180（速率 0.60 条/秒，较上一窗 +130）"


def test_conditions_render_one_line_each():
    text = format_hit_line(
        {
            "count": 180,
            "conditions": [
                {"func": "count_uniq", "field": "client_ip", "current": 63, "value": 63, "compare": {"kind": "absolute"}},
                {
                    "func": "count",
                    "field": "_msg",
                    "current": 180,
                    "baseline": 120,
                    "value": 50.0,
                    "compare": {"kind": "percent", "to": "offset_24h"},
                },
                {
                    "func": "ratio",
                    "field": "_msg",
                    "value": 7.2,
                    "params": {"filter": "status:500"},
                    "hit": 13,
                    "total": 180,
                    "compare": {"kind": "absolute"},
                },
                {
                    "func": "quantile",
                    "field": "duration",
                    "current": 2310.5,
                    "value": 2310.5,
                    "params": {"quantile": 0.95},
                    "compare": {"kind": "absolute"},
                },
            ],
        }
    )
    assert text.splitlines() == [
        "命中条数：180",
        "去重计数(client_ip)：63",
        "计数：180（较 24 小时前 +50.0%，对照 120）",
        "占比(status:500)：7.2%（13 / 180）",
        "P95(duration)：2310.50",
    ]
