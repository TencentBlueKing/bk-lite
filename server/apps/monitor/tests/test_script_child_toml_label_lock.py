"""脚本 child TOML 契约：inputs.exec 之后的 processor 强制 instance_id。"""

import tomllib

from apps.monitor.services.custom_script_plugin import (
    DEFAULT_SCRIPT_CHILD_TEMPLATE,
    RESERVED_SCRIPT_TAG_KEYS,
    CustomScriptPluginService,
)


PLATFORM_INSTANCE_ID = "platform-instance-1"

RENDER_FIXTURE = {
    "instance_id": PLATFORM_INSTANCE_ID,
    "instance_type": "host",
    "plugin_id": "script-plugin-1",
    "config_id": "CFG1",
    "interval": 60,
    "timeout": 10,
    "username": "nobody",
}


class FakeMetric:
    def __init__(self, name, tags=None, fields=None, time=0):
        self.name = name
        self.tags = tags or {}
        self.fields = fields or {}
        self.time = time


def _require_processor_after_exec(toml_text: str) -> str:
    exec_idx = toml_text.index("[[inputs.exec]]")
    after_exec = toml_text[exec_idx:]
    assert "[[processors.starlark]]" in after_exec
    processor = after_exec[after_exec.index("[[processors.starlark]]") :]
    assert 'metric.tags["instance_id"] = reserved_instance_id' in processor
    assert 'reserved_instance_id = "{{ instance_id }}"' in processor or f'reserved_instance_id = "{PLATFORM_INSTANCE_ID}"' in processor
    return processor


def _load_starlark_apply(processor: dict):
    namespace = dict(processor["constants"])
    exec(processor["source"], namespace)
    return namespace["apply"]


def test_script_child_template_locks_instance_id_after_exec():
    template = CustomScriptPluginService.child_template()
    assert template == DEFAULT_SCRIPT_CHILD_TEMPLATE
    assert template.index("[[inputs.exec]]") < template.index("[[processors.starlark]]")
    processor = _require_processor_after_exec(template)
    assert 'reserved_instance_id = "{{ instance_id }}"' in processor
    assert "[inputs.exec.tags]" in template
    tags_block = template[template.index("[inputs.exec.tags]") : template.index("[[processors.starlark]]")]
    assert "instance_id = \"{{ instance_id }}\"" in tags_block
    assert "[[processors.starlark]]" not in tags_block

    rendered = CustomScriptPluginService.render_child_template(RENDER_FIXTURE)
    assert rendered.index("[[inputs.exec]]") < rendered.index("[[processors.starlark]]")
    rendered_processor = _require_processor_after_exec(rendered)
    assert f'reserved_instance_id = "{PLATFORM_INSTANCE_ID}"' in rendered_processor
    assert 'reserved_instance_id = "{{ instance_id }}"' not in rendered

    parsed = tomllib.loads(rendered)
    exec_inputs = parsed["inputs"]["exec"]
    assert isinstance(exec_inputs, list) and exec_inputs
    exec_cfg = exec_inputs[0]
    assert exec_cfg["commands"] == ["/opt/fusion-collectors/bin/bklite-script-wrapper"]
    assert exec_cfg["data_format"] == "prometheus"
    env_values = exec_cfg["environment"]
    assert "BK_SCRIPT_CONFIG_ID=CFG1" in env_values
    assert "BK_SCRIPT_INSTANCE_ID=platform-instance-1" in env_values
    assert "BK_SCRIPT_BODY=${SCRIPT_BODY__CFG1}" in env_values
    assert "BK_SCRIPT_USER=nobody" in env_values
    assert all("SCRIPT_BODY=" not in item or item.startswith("BK_SCRIPT_BODY=${") for item in env_values)
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


def test_script_child_template_uses_windows_wrapper_path():
    rendered = CustomScriptPluginService.render_child_template({**RENDER_FIXTURE, "operating_system": "windows"})
    parsed = tomllib.loads(rendered)
    assert parsed["inputs"]["exec"][0]["commands"] == [r"C:\fusion-collectors\bin\bklite-script-wrapper.exe"]
    assert parsed["inputs"]["exec"][0]["data_format"] == "prometheus"
