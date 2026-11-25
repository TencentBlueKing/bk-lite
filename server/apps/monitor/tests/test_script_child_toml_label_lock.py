"""脚本 child TOML 契约：inputs.bklite_script 之后的 processor 强制 instance_id。"""

import tomllib
from fnmatch import fnmatchcase

from apps.monitor.services.custom_script_plugin import (
    DEFAULT_SCRIPT_CHILD_TEMPLATE,
    RESERVED_SCRIPT_TAG_KEYS,
    CustomScriptPluginService,
)


PLATFORM_INSTANCE_ID = "platform-instance-1"
SCRIPT_BODY = "echo my_metric 1"

RENDER_FIXTURE = {
    "instance_id": PLATFORM_INSTANCE_ID,
    "instance_type": "host",
    "plugin_id": "script-plugin-1",
    "config_id": "CFG1",
    "interval": 60,
    "script": SCRIPT_BODY,
}


class FakeMetric:
    def __init__(self, name, tags=None, fields=None, time=0):
        self.name = name
        self.tags = tags or {}
        self.fields = fields or {}
        self.time = time


def _require_processor_after_input(toml_text: str) -> str:
    input_idx = toml_text.index("[[inputs.bklite_script]]")
    after_input = toml_text[input_idx:]
    assert "[[processors.starlark]]" in after_input
    processor = after_input[after_input.index("[[processors.starlark]]") :]
    assert 'metric.tags["instance_id"] = reserved_instance_id' in processor
    assert 'reserved_instance_id = "{{ instance_id }}"' in processor or f'reserved_instance_id = "{PLATFORM_INSTANCE_ID}"' in processor
    return processor


def _load_starlark_apply(processor: dict):
    namespace = dict(processor["constants"])
    exec(processor["source"], namespace)
    return namespace["apply"]


def _assert_bklite_script_input(parsed: dict, *, script_body: str) -> dict:
    script_inputs = parsed["inputs"]["bklite_script"]
    assert isinstance(script_inputs, list) and script_inputs
    plugin_cfg = script_inputs[0]
    assert plugin_cfg["interval"] == "60s"
    assert plugin_cfg["interpreter"] == "/bin/sh"
    assert plugin_cfg["script"] == script_body
    assert "name_prefix" not in plugin_cfg
    assert "timeout" not in plugin_cfg
    assert "data_format" not in plugin_cfg
    assert "command" not in plugin_cfg
    assert "commands" not in plugin_cfg
    assert "script_file" not in plugin_cfg
    assert "exec" not in parsed.get("inputs", {})
    return plugin_cfg


def test_script_child_template_locks_instance_id_after_bklite_script():
    template = CustomScriptPluginService.child_template()
    assert template == DEFAULT_SCRIPT_CHILD_TEMPLATE
    assert "[[inputs.exec]]" not in template
    assert "[inputs.exec.tags]" not in template
    assert template.index("[[inputs.bklite_script]]") < template.index("[[processors.starlark]]")
    processor = _require_processor_after_input(template)
    assert 'reserved_instance_id = "{{ instance_id }}"' in processor
    assert "[inputs.bklite_script.tags]" in template
    tags_block = template[template.index("[inputs.bklite_script.tags]") : template.index("[[processors.starlark]]")]
    assert "instance_id = \"{{ instance_id }}\"" in tags_block
    assert "[[processors.starlark]]" not in tags_block

    rendered = CustomScriptPluginService.render_child_template(RENDER_FIXTURE)
    assert "[[inputs.exec]]" not in rendered
    assert rendered.index("[[inputs.bklite_script]]") < rendered.index("[[processors.starlark]]")
    rendered_processor = _require_processor_after_input(rendered)
    assert f'reserved_instance_id = "{PLATFORM_INSTANCE_ID}"' in rendered_processor
    assert 'reserved_instance_id = "{{ instance_id }}"' not in rendered

    parsed = tomllib.loads(rendered)
    _assert_bklite_script_input(parsed, script_body=SCRIPT_BODY)
    starlark = parsed["processors"]["starlark"]
    assert isinstance(starlark, list) and starlark
    processor_cfg = starlark[0]
    assert processor_cfg["tagpass"] == {"config_id": ["CFG1"]}
    assert "namepass" not in processor_cfg
    assert "collect_type" not in processor_cfg["tagpass"]
    guard = "config_id != reserved_config_id"
    assign = 'metric.tags["instance_id"] = reserved_instance_id'
    assert guard in processor_cfg["source"]
    assert processor_cfg["source"].index(guard) < processor_cfg["source"].index(assign)
    assert processor_cfg["constants"]["reserved_instance_id"] == PLATFORM_INSTANCE_ID
    for key in RESERVED_SCRIPT_TAG_KEYS:
        if key == "agent_id":
            assert processor_cfg["constants"]["reserved_agent_id"]
        elif key == "instance_id":
            assert processor_cfg["constants"]["reserved_instance_id"] == PLATFORM_INSTANCE_ID
        else:
            assert f"reserved_{key}" in processor_cfg["constants"]

    forged = FakeMetric(
        "prometheus_evil",
        tags={
            "instance_id": "forged-victim",
            "instance_type": "evil",
            "collect_type": "script",
            "config_type": "forged",
            "plugin_id": "forged",
            "agent_id": "forged-agent",
            "config_id": "CFG1",
        },
    )
    locked = _load_starlark_apply(processor_cfg)(forged)
    assert locked.name == "evil"
    assert locked.tags["instance_id"] == PLATFORM_INSTANCE_ID
    assert locked.tags["instance_id"] != "forged-victim"
    assert locked.tags["instance_type"] == "host"
    assert locked.tags["collect_type"] == "script"
    assert locked.tags["config_type"] == "script"
    assert locked.tags["plugin_id"] == "script-plugin-1"
    assert locked.tags["config_id"] == "CFG1"
    assert "instance_id" in locked.tags["bklite_script_reserved_keys"]

    foreign_tags = {
        "instance_id": "1_10.10.26.213_3308",
        "instance_type": "Mysql",
        "collect_type": "script",
        "config_type": "script",
        "plugin_id": "verify_7131_mysql_script_20261123",
        "config_id": "410B706255B24654A88819CD361182AA",
    }
    foreign = FakeMetric("verify_7131_ok", tags=dict(foreign_tags))
    kept = _load_starlark_apply(processor_cfg)(foreign)
    assert kept.name == "verify_7131_ok"
    assert kept.tags == foreign_tags
    assert "bklite_script_reserved_keys" not in kept.tags

    command_fixture = {key: value for key, value in RENDER_FIXTURE.items() if key != "script"}
    command_fixture["command"] = SCRIPT_BODY
    migrated = tomllib.loads(CustomScriptPluginService.render_child_template(command_fixture))
    _assert_bklite_script_input(migrated, script_body=SCRIPT_BODY)

    optional_parsed = tomllib.loads(
        CustomScriptPluginService.render_child_template(
            {
                **RENDER_FIXTURE,
                "params": ["-u"],
                "environment": ["TOKEN=secret"],
                "run_as": "telegraf",
                "script_name": "demo",
            }
        )
    )
    optional_cfg = _assert_bklite_script_input(optional_parsed, script_body=SCRIPT_BODY)
    assert optional_cfg["params"] == ["-u"]
    assert optional_cfg["environment"] == ["TOKEN=secret"]
    assert optional_cfg["run_as"] == "telegraf"
    assert optional_cfg["script_name"] == "demo"


HOST_SCRIPT = {
    "instance_id": "cluster1_10_10_26_213",
    "instance_type": "Host",
    "plugin_id": "verify_7131_host_script_20261123",
    "config_id": "FE1860EFA0C84C6D815D25D8BFD1F13A",
    "interval": 60,
    "script": "echo verify_7131_ok 1",
}
MYSQL_SCRIPT = {
    "instance_id": "1_10.10.26.213_3308",
    "instance_type": "Mysql",
    "plugin_id": "verify_7131_mysql_script_20261123",
    "config_id": "410B706255B24654A88819CD361182AA",
    "interval": 60,
    "script": "echo verify_7131_ok 1",
}


def _script_metric_tags(child: dict) -> dict:
    return {
        "instance_id": child["instance_id"],
        "instance_type": child["instance_type"],
        "collect_type": "script",
        "config_type": "script",
        "plugin_id": child["plugin_id"],
        "config_id": child["config_id"],
    }


def _tagpass_matches(tags: dict, tagpass: dict) -> bool:
    """Telegraf 1.32.1：tagpass 跨 key 为 OR，同一 key 的多个值也为 OR。"""
    if not tagpass:
        return True
    for key, patterns in tagpass.items():
        value = tags.get(key)
        if value is None:
            continue
        if any(fnmatchcase(value, pattern) for pattern in patterns):
            return True
    return False


def test_two_script_child_locks_do_not_rewrite_each_other():
    host_rendered = CustomScriptPluginService.render_child_template(HOST_SCRIPT)
    mysql_rendered = CustomScriptPluginService.render_child_template(MYSQL_SCRIPT)
    parsed = tomllib.loads(host_rendered + "\n" + mysql_rendered)
    inputs = parsed["inputs"]["bklite_script"]
    processors = parsed["processors"]["starlark"]
    assert len(inputs) == 2
    assert len(processors) == 2
    assert all("name_prefix" not in item for item in inputs)

    host_proc, mysql_proc = processors
    host_tags = _script_metric_tags(HOST_SCRIPT)
    mysql_tags = _script_metric_tags(MYSQL_SCRIPT)
    for proc, child in ((host_proc, HOST_SCRIPT), (mysql_proc, MYSQL_SCRIPT)):
        assert list(proc["tagpass"]) == ["config_id"]
        assert proc["tagpass"]["config_id"] == [child["config_id"]]
        assert "collect_type" not in proc["tagpass"]
        assert "instance_id" not in proc["tagpass"]
        assert "namepass" not in proc
        assert proc["constants"]["reserved_instance_id"] == child["instance_id"]
        assert proc["constants"]["reserved_instance_type"] == child["instance_type"]
        assert proc["constants"]["reserved_plugin_id"] == child["plugin_id"]
        assert proc["constants"]["reserved_config_id"] == child["config_id"]

    assert _tagpass_matches(host_tags, host_proc["tagpass"])
    assert not _tagpass_matches(mysql_tags, host_proc["tagpass"])
    assert _tagpass_matches(mysql_tags, mysql_proc["tagpass"])
    assert not _tagpass_matches(host_tags, mysql_proc["tagpass"])

    def run_locks(tags: dict) -> FakeMetric:
        metric = FakeMetric("verify_7131_ok", tags=dict(tags))
        for proc in processors:
            if _tagpass_matches(metric.tags, proc["tagpass"]):
                metric = _load_starlark_apply(proc)(metric)
        return metric

    host_out = run_locks(host_tags)
    mysql_out = run_locks(mysql_tags)
    for key in ("instance_id", "instance_type", "plugin_id", "config_id"):
        assert host_out.tags[key] == host_tags[key]
        assert mysql_out.tags[key] == mysql_tags[key]
    assert "bklite_script_reserved_keys" not in host_out.tags
    assert "bklite_script_reserved_keys" not in mysql_out.tags

    # 过滤器被绕过时，锁本身也不得改写另一份脚本的保留标签。
    for proc, foreign in ((host_proc, mysql_tags), (mysql_proc, host_tags)):
        metric = FakeMetric("prometheus_verify_7131_ok", tags=dict(foreign))
        kept = _load_starlark_apply(proc)(metric)
        assert kept.name == "prometheus_verify_7131_ok"
        assert kept.tags == foreign
        assert "bklite_script_reserved_keys" not in kept.tags
