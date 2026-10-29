"""自定义正则校验失败不得把提交值写进错误日志。"""

import logging

import pytest

from apps.cmdb.validators.field_validator import FieldValidator
from apps.core.exceptions.base_app_exception import BaseAppException

SENTINEL = "td_probe_lowercase"
CMDB_LOGGER = "cmdb"
EXCEPTION_LOGGER = "apps.core.exceptions.base_app_exception"
WATCHED_LOGGERS = {CMDB_LOGGER, EXCEPTION_LOGGER}
EXPECTED_MISMATCH = f"值 '{SENTINEL}' 不符合自定义正则表达式规则"


def _attr(attr_id="asset_code", custom_regex=r"^[A-Z]+$"):
    return {
        "attr_id": attr_id,
        "attr_name": "资产编码",
        "attr_type": "str",
        "option": {
            "validation_type": "custom",
            "custom_regex": custom_regex,
        },
    }


def _render(record: logging.LogRecord) -> str:
    return logging.Formatter("%(levelname)s %(name)s %(message)s").format(record)


def _watched(caplog):
    return [record for record in caplog.records if record.name in WATCHED_LOGGERS]


def _watch(caplog):
    caplog.set_level(logging.ERROR)


def test_custom_regex_mismatch_keeps_error_without_logging_value(caplog):
    _watch(caplog)

    errors = FieldValidator.validate_instance_data(
        {"asset_code": SENTINEL},
        [_attr()],
    )

    assert errors == [
        {
            "field": "asset_code",
            "field_name": "资产编码",
            "value": SENTINEL,
            "error": EXPECTED_MISMATCH,
        }
    ]
    assert "正则表达式校验异常" not in errors[0]["error"]
    assert "字段校验失败" not in errors[0]["error"]
    for record in _watched(caplog):
        rendered = _render(record)
        assert SENTINEL not in record.getMessage()
        assert SENTINEL not in (record.exc_text or "")
        assert SENTINEL not in rendered
        assert record.exc_info is None
        assert "Traceback" not in rendered


def test_custom_regex_mismatch_reraises_original_exception(caplog):
    _watch(caplog)
    constraint = {"validation_type": "custom", "custom_regex": r"^[A-Z]+$"}

    with pytest.raises(BaseAppException) as caught:
        FieldValidator.validate_string(SENTINEL, constraint)

    assert type(caught.value) is BaseAppException
    assert caught.value.message == EXPECTED_MISMATCH
    assert caught.value.ERROR_CODE == "0000000"

    with pytest.raises(BaseAppException) as caught:
        FieldValidator.validate_field_by_attr(SENTINEL, _attr())

    assert type(caught.value) is BaseAppException
    assert caught.value.message == EXPECTED_MISMATCH
    assert caught.value.ERROR_CODE == "0000000"
    assert "字段校验失败" not in caught.value.message
    for record in _watched(caplog):
        rendered = _render(record)
        assert SENTINEL not in record.getMessage()
        assert SENTINEL not in (record.exc_text or "")
        assert SENTINEL not in rendered
        assert "Traceback" not in rendered


def test_matching_custom_regex_still_passes():
    errors = FieldValidator.validate_instance_data({"asset_code": "ABC"}, [_attr()])
    assert errors == []


def test_invalid_custom_regex_still_returns_error():
    errors = FieldValidator.validate_instance_data(
        {"asset_code": "ABC"},
        [_attr(custom_regex="[")],
    )

    assert len(errors) == 1
    assert errors[0]["field"] == "asset_code"
    assert errors[0]["value"] == "ABC"
    assert errors[0]["error"]


def test_unexpected_custom_regex_failure_logs_one_traceback_without_value(monkeypatch, caplog):
    submitted = "td_probe_unexpected"
    exception_text = f"compiler blew up {submitted}"

    def explode(pattern, flags=0):
        raise RuntimeError(exception_text)

    monkeypatch.setattr("apps.cmdb.validators.field_validator.re.compile", explode)
    _watch(caplog)

    errors = FieldValidator.validate_instance_data(
        {"asset_code": submitted},
        [_attr()],
    )

    assert len(errors) == 1
    assert errors[0]["field"] == "asset_code"
    assert errors[0]["value"] == submitted
    watched = _watched(caplog)
    rendered = [_render(record) for record in watched]
    assert sum("Traceback (most recent call last)" in text for text in rendered) == 1
    for record in watched:
        message = record.getMessage()
        assert submitted not in message
        assert exception_text not in message


def test_falkordb_create_entity_custom_regex_mismatch_keeps_message_without_exception_log(caplog):
    from apps.cmdb.graph.falkordb import FalkorDBClient

    _watch(caplog)
    client = FalkorDBClient()

    with pytest.raises(BaseAppException) as caught:
        client.create_entity(
            label="instance",
            properties={"asset_code": SENTINEL},
            check_attr_map={},
            exist_items=[],
            attrs=[_attr()],
        )

    assert type(caught.value) is BaseAppException
    assert EXPECTED_MISMATCH in caught.value.message
    for record in caplog.records:
        if record.name != EXCEPTION_LOGGER:
            continue
        rendered = _render(record)
        assert SENTINEL not in record.getMessage()
        assert SENTINEL not in (record.exc_text or "")
        assert SENTINEL not in rendered
        assert record.exc_info is None
        assert "Traceback" not in rendered


def test_base_app_exception_logs_by_default_and_skips_when_disabled(caplog):
    _watch(caplog)

    with pytest.raises(BaseAppException) as caught:
        raise BaseAppException("plain-default-message")

    assert caught.value.ERROR_CODE == "0000000"
    assert any(
        record.name == EXCEPTION_LOGGER and "plain-default-message" in record.getMessage()
        for record in caplog.records
    )

    caplog.clear()
    with pytest.raises(BaseAppException) as caught:
        raise BaseAppException(EXPECTED_MISMATCH, log=False)

    assert caught.value.message == EXPECTED_MISMATCH
    assert caught.value.ERROR_CODE == "0000000"
    assert not [record for record in caplog.records if record.name == EXCEPTION_LOGGER]
