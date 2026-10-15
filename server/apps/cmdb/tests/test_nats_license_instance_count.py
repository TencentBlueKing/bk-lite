"""CMDB 许可用量 NATS 接口，不影响公共 model_inst_count。"""

import logging

import pytest

from apps.cmdb.nats import nats as N
from apps.cmdb.services.instance import InstanceManage


class _FakeLanguage:
    def __init__(self, language):
        self.language = language

    def get_val(self, _type, key):
        return {"host": "主机", "switch": "交换机"}.get(key)


def _assert_safe_warning(record, message, args, sentinel, original):
    assert record.msg == message
    assert record.args == args
    assert sentinel not in record.getMessage()
    exc_type, exc_value, exc_tb = record.exc_info
    assert exc_type.__name__ == "SafeLogException"
    assert str(exc_value) == type(original).__name__
    assert exc_value is not original
    assert exc_tb is original.__traceback__
    assert str(original) == sentinel
    rendered = logging.Formatter().format(record)
    assert sentinel not in rendered
    assert "Traceback" in rendered


@pytest.mark.unit
def test_license_cmdb_instance_count_uses_license_counter(monkeypatch):
    monkeypatch.setattr(
        InstanceManage,
        "license_instance_count",
        classmethod(lambda cls: {"host": 4, "switch": 1}),
    )
    monkeypatch.setattr("apps.cmdb.language.service.SettingLanguage", _FakeLanguage)

    out = N.license_cmdb_instance_count(language="zh-Hans")

    assert out["data"] == {"host": 4, "switch": 1}
    assert out["labels"] == {"host": "主机", "switch": "交换机"}


@pytest.mark.unit
def test_license_cmdb_labels_use_stored_name_and_keep_counts_on_lookup_failure(monkeypatch, caplog):
    sentinel = "SECRET-GRAPH-hwcloud-payload"

    class _PartialLanguage(_FakeLanguage):
        def get_val(self, _type, key):
            return {"host": "主机"}.get(key)

    raised = {}

    def search_model_info(model_id):
        if model_id == "switch":
            return {"model_name": "交换机"}
        error = RuntimeError(sentinel)
        raised["error"] = error
        raise error

    monkeypatch.setattr(
        InstanceManage,
        "license_instance_count",
        classmethod(lambda cls: {"host": 4, "switch": 1, "hwcloud_ecs": 2}),
    )
    monkeypatch.setattr("apps.cmdb.language.service.SettingLanguage", _PartialLanguage)
    monkeypatch.setattr(N.ModelManage, "search_model_info", staticmethod(search_model_info))

    with caplog.at_level(logging.WARNING, logger="cmdb"):
        out = N.license_cmdb_instance_count(language=None)

    assert out["data"] == {"host": 4, "switch": 1, "hwcloud_ecs": 2}
    assert out["labels"] == {"host": "主机", "switch": "交换机"}
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    _assert_safe_warning(
        warnings[0],
        "event=license_cmdb_label_skipped model_id=%s failed_stage=%s error_type=%s",
        ("hwcloud_ecs", "search_model_info", "RuntimeError"),
        sentinel,
        raised["error"],
    )
    assert sentinel not in caplog.text


@pytest.mark.unit
def test_license_cmdb_language_load_failure_keeps_counts(monkeypatch, caplog):
    sentinel = "SECRET-CMDB-LANGUAGE-PAYLOAD"

    raised = {}

    class _BoomLanguage:
        def __init__(self, language):
            error = RuntimeError(sentinel)
            raised["error"] = error
            raise error

    monkeypatch.setattr(
        InstanceManage,
        "license_instance_count",
        classmethod(lambda cls: {"host": 4}),
    )
    monkeypatch.setattr("apps.cmdb.language.service.SettingLanguage", _BoomLanguage)

    with caplog.at_level(logging.WARNING, logger="cmdb"):
        out = N.license_cmdb_instance_count(language="zh-Hans")

    assert out["data"] == {"host": 4}
    assert out["labels"] == {}
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    _assert_safe_warning(
        warnings[0],
        "event=license_cmdb_labels_skipped failed_stage=%s error_type=%s",
        ("load_language", "RuntimeError"),
        sentinel,
        raised["error"],
    )
    assert sentinel not in caplog.text


@pytest.mark.unit
def test_license_cmdb_translation_failure_keeps_counts(monkeypatch, caplog):
    sentinel = "SECRET-CMDB-TRANSLATION-PAYLOAD"
    raised = {}

    class _BoomTranslation:
        def __init__(self, language):
            self.language = language

        def get_val(self, _type, key):
            error = RuntimeError(sentinel)
            raised["error"] = error
            raise error

    monkeypatch.setattr(
        InstanceManage,
        "license_instance_count",
        classmethod(lambda cls: {"host": 4}),
    )
    monkeypatch.setattr("apps.cmdb.language.service.SettingLanguage", _BoomTranslation)

    with caplog.at_level(logging.WARNING, logger="cmdb"):
        out = N.license_cmdb_instance_count(language="en")

    assert out["data"] == {"host": 4}
    assert out["labels"] == {}
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    _assert_safe_warning(
        warnings[0],
        "event=license_cmdb_label_skipped model_id=%s failed_stage=%s error_type=%s",
        ("host", "load_translation", "RuntimeError"),
        sentinel,
        raised["error"],
    )
    assert sentinel not in caplog.text


@pytest.mark.unit
def test_license_cmdb_missing_language_uses_user_locale_only(monkeypatch):
    seen = {}

    class _SeenLanguage:
        def __init__(self, language):
            seen["language"] = language

        def get_val(self, _type, key):
            return "主机" if key == "host" else None

    monkeypatch.setattr(
        InstanceManage,
        "license_instance_count",
        classmethod(lambda cls: {"host": 1}),
    )
    monkeypatch.setattr("apps.cmdb.language.service.SettingLanguage", _SeenLanguage)

    N.license_cmdb_instance_count(user_info={"language": "en", "LANGUAGE_CODE": "en"})
    assert seen["language"] is None

    N.license_cmdb_instance_count(user_info={"locale": "en", "language": "zh-Hans"})
    assert seen["language"] == "en"


@pytest.mark.unit
def test_public_model_inst_count_still_counts_all_models(monkeypatch):
    monkeypatch.setattr(
        InstanceManage,
        "model_inst_count",
        classmethod(lambda cls, permissions_map, creator="": {"host": 4, "mysql": 9}),
    )

    out = N.model_inst_count()

    assert out["data"]["mysql"] == 9
    assert out["data"]["host"] == 4
