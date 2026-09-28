"""脚本 child TOML 契约：inputs.bklite_script 之后的 processor 强制 instance_id。"""

import tomllib

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
    assert plugin_cfg["name_prefix"] == "bklite_script_CFG1_"
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
    assert processor_cfg["namepass"] == ["bklite_script_CFG1_*"]
    assert processor_cfg["constants"]["reserved_instance_id"] == PLATFORM_INSTANCE_ID
    for key in RESERVED_SCRIPT_TAG_KEYS:
        if key == "agent_id":
            assert processor_cfg["constants"]["reserved_agent_id"]
        elif key == "instance_id":
            assert processor_cfg["constants"]["reserved_instance_id"] == PLATFORM_INSTANCE_ID
        else:
            assert f"reserved_{key}" in processor_cfg["constants"]

    forged = FakeMetric(
        "evil",
        tags={
            "instance_id": "forged-victim",
            "instance_type": "evil",
            "collect_type": "forged",
            "config_type": "forged",
            "plugin_id": "forged",
            "agent_id": "forged-agent",
        },
    )
    locked = _load_starlark_apply(processor_cfg)(forged)
    assert locked.tags["instance_id"] == PLATFORM_INSTANCE_ID
    assert locked.tags["instance_id"] != "forged-victim"
    assert locked.tags["instance_type"] == "host"
    assert locked.tags["collect_type"] == "script"
    assert locked.tags["config_type"] == "script"
    assert locked.tags["plugin_id"] == "script-plugin-1"

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
