import json
from contextlib import nullcontext

from apps.log.constants.plugin import PluginConstants
from apps.log.management.services import plugin


def _write_collect_type(root, collector, name, content):
    plugin_dir = root / collector / name
    plugin_dir.mkdir(parents=True)
    config_path = plugin_dir / "collect_type.json"
    if isinstance(content, dict):
        config_path.write_text(json.dumps(content), encoding="utf-8")
    else:
        config_path.write_text(content, encoding="utf-8")


class _CollectTypeObjects:
    def __init__(self):
        self.updated = []
        self.excluded = []
        self.deleted = False

    def update_or_create(self, **kwargs):
        self.updated.append(kwargs)

    def exclude(self, condition):
        self.excluded.append(condition)
        return self

    def delete(self):
        self.deleted = True
        return 1, {"log.CollectType": 1}


def test_migrate_collect_type_does_not_write_when_any_config_is_invalid(tmp_path, monkeypatch):
    _write_collect_type(
        tmp_path,
        "Vector",
        "valid",
        {
            "name": "valid",
            "collector": "Vector",
            "icon": "valid",
        },
    )
    _write_collect_type(tmp_path, "Vector", "invalid", "{invalid json")
    monkeypatch.setattr(PluginConstants, "DIRECTORY", str(tmp_path))
    objects = _CollectTypeObjects()
    monkeypatch.setattr(plugin.CollectType, "objects", objects)
    monkeypatch.setattr(plugin.transaction, "atomic", nullcontext)

    try:
        plugin.migrate_collect_type()
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("invalid plugin configuration must fail the synchronization")

    assert objects.updated == []
    assert objects.excluded == []
    assert objects.deleted is False


def test_migrate_collect_type_updates_and_cleans_up_after_all_configs_parse(tmp_path, monkeypatch):
    _write_collect_type(
        tmp_path,
        "Vector",
        "valid",
        {
            "name": "valid",
            "collector": "Vector",
            "icon": "new",
        },
    )
    monkeypatch.setattr(PluginConstants, "DIRECTORY", str(tmp_path))
    objects = _CollectTypeObjects()
    monkeypatch.setattr(plugin.CollectType, "objects", objects)
    monkeypatch.setattr(plugin.transaction, "atomic", nullcontext)

    plugin.migrate_collect_type()

    assert objects.updated == [
        {
            "name": "valid",
            "collector": "Vector",
            "defaults": {"name": "valid", "collector": "Vector", "icon": "new"},
        }
    ]
    assert len(objects.excluded) == 1
    assert objects.deleted is True
