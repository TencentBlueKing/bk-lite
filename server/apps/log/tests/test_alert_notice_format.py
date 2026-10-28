"""命中行：有 conditions 时逐条渲染，没有时保持第一批格式。"""

from types import SimpleNamespace

from apps.log.services.alert_notice_format import format_aggregate_notice, format_hit_line, notice_context


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


def test_no_data_notice_second_line_omits_samples_and_keeps_links():
    raw = {
        "aggregate_result": {
            "count": 0,
            "no_data": True,
            "baseline": {
                "to": "previous_window",
                "status": "ok",
                "values": {"count__msg": 300},
            },
        },
        "samples": [{"message": "should-not-appear"}],
        "jump_query": {"query": "level:error", "window_start": 1700000000, "window_end": 1700000300},
    }
    event = SimpleNamespace(
        id=None,
        alert_id=None,
        event_time="2026-10-27T08:00:00Z",
        content="无数据：host-b 断流",
        raw_data={
            "aggregate_result": raw["aggregate_result"],
            "samples": [],
            "jump_query": raw["jump_query"],
        },
    )
    policy = SimpleNamespace(name="断流策略", log_groups=["g1"])
    title, content = format_aggregate_notice(
        event,
        policy,
        raw,
        raw["jump_query"],
        base_url="https://example.test",
    )
    assert title == "【日志告警通知】"
    assert content.splitlines()[1] == "本窗无日志，上一窗 300 条"
    assert "样本" not in content
    assert "should-not-appear" not in content
    assert "命中条数" not in content
    assert "https://example.test/log/search?" in content
    assert "https://example.test/log/event/alert" in content
    context = notice_context(event, policy, base_url="https://example.test")
    assert context["aggregate_result"] == raw["aggregate_result"]
    assert context["aggregate_result"]["no_data"] is True
