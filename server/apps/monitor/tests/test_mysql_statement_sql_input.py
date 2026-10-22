"""MySQL 语句摘要改由 inputs.sql 落点。

inputs.mysql 的 digest 查询会丢掉 SCHEMA_NAME 为空的行，DIGEST 为 NULL 时 Scan
失败导致整批语句指标都不发出。等待事件不走这条查询，所以仍有点。
"""
from pathlib import Path

import tomllib

from apps.monitor.utils.plugin_controller import Controller

SERVER_ROOT = Path(__file__).resolve().parents[3]
MYSQL_TEMPLATE = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf" / "database" / "mysql" / "mysql.child.toml.j2"


def _render(statements):
    text = MYSQL_TEMPLATE.read_text(encoding="utf-8")
    rendered = Controller({}).render_template(
        text,
        {
            "username": "root",
            "config_id": "4acfff1a",
            "host": "10.10.26.213",
            "port": "3309",
            "interval": "60",
            "instance_id": "1_10.10.26.213_3309",
            "instance_type": "mysql",
            "gather_perf_events_statements": statements,
            "gather_event_waits": True,
            "gather_replica_status": True,
        },
    )
    return rendered, tomllib.loads(rendered)


def test_statements_switch_renders_sql_input_with_dashboard_names():
    rendered, parsed = _render(True)
    mysql = parsed["inputs"]["mysql"][0]
    assert mysql["gather_perf_events_statements"] is False
    assert mysql["gather_event_waits"] is True
    assert "slave_seconds_behind_source" in mysql["fieldinclude"]
    assert "events_statements_seconds_total" in mysql["fieldinclude"]
    assert "events_waits_seconds_total" in mysql["fieldinclude"]

    sql = parsed["inputs"]["sql"][0]
    assert sql["driver"] == "mysql"
    assert sql["disconnected_servers_behavior"] == "ignore"
    assert sql["tags"]["instance_id"] == "1_10.10.26.213_3309"
    assert "${PASSWORD__4acfff1a}" in sql["dsn"]
    query = sql["query"][0]
    assert query["measurement"] == "mysql_perf_schema"
    assert query["tag_columns_include"] == ["schema", "digest", "digest_text"]
    assert "events_statements_seconds_total" in query["field_columns_float"]
    assert "IFNULL(DIGEST, 'none')" in query["query"]
    assert "SCHEMA_NAME NOT IN" not in query["query"]
    assert "events_statements_summary_by_digest" in query["query"]
    assert 'namepass = ["mysql"]' in rendered
    assert "slave_replica_io_running_int" in rendered


def test_statements_switch_off_omits_sql_input():
    rendered, parsed = _render(False)
    assert "sql" not in parsed["inputs"]
    assert "events_statements_summary_by_digest" not in rendered
    assert parsed["inputs"]["mysql"][0]["gather_perf_events_statements"] is False
    assert parsed["inputs"]["mysql"][0]["gather_event_waits"] is True
