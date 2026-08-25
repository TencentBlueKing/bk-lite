"""Regression tests for predict debug logging privacy (Issue #3853)."""

import asyncio
from io import StringIO
from unittest.mock import MagicMock, patch

import pandas as pd
from loguru import logger as real_logger

from tests.test_feature_importance import _load_service_module, _make_service


def test_predict_debug_logs_do_not_include_request_texts():
    """predict() should log metadata only, never raw or processed request text."""
    service_mod = _load_service_module()
    logger = MagicMock()

    sensitive_text = "user=jane ip=10.0.0.8 token=secret-alert-text"
    oversized_text = "A" * (service_mod.MAX_TEXT_LENGTH + 3)
    model = MagicMock()
    model.predict.return_value = pd.DataFrame(
        [
            {
                "prediction": "sensitive",
                "probability": 0.95,
                "prob_sensitive": 0.95,
                "prob_normal": 0.05,
            },
            {
                "prediction": "normal",
                "probability": 0.75,
                "prob_sensitive": 0.25,
                "prob_normal": 0.75,
            },
        ]
    )

    svc = _make_service(model=model)
    svc.config.source = "dummy"

    with patch.dict(svc.predict.__func__.__globals__, {"logger": logger}):
        response = asyncio.run(
            svc.predict(
                [sensitive_text, oversized_text],
                config={"return_feature_importance": False},
            )
        )

    assert response.success is True
    model.predict.assert_called_once()
    assert model.predict.call_args.args[0][0] == sensitive_text
    assert len(model.predict.call_args.args[0][1]) == service_mod.MAX_TEXT_LENGTH

    debug_output = "\n".join(str(call) for call in logger.debug.call_args_list)
    assert sensitive_text not in debug_output
    assert "secret-alert-text" not in debug_output
    assert oversized_text[:120] not in debug_output
    assert "event=text_classification_preprocessed texts={} truncated={}" in debug_output
    assert "event=text_classification_model_predict_started texts={} truncated={}" in debug_output
    assert "call('event=text_classification_preprocessed texts={} truncated={}', 2, 1)" in debug_output
    assert any(call.args[0].startswith("event=text_classification_completed") for call in logger.info.call_args_list)


def test_predict_failure_keeps_error_response_and_uses_one_sanitized_traceback():
    _load_service_module()
    secret = "model-response-secret-must-not-enter-logs"
    frame_secret = "frame-local-secret-must-not-enter-logs"
    model = MagicMock()
    error = RuntimeError(secret)
    def fail_with_sensitive_local(*_args, **_kwargs):
        sensitive_local = frame_secret
        assert sensitive_local
        raise error

    model.predict.side_effect = fail_with_sensitive_local
    svc = _make_service(model=model)
    svc.config.source = "dummy"
    output = StringIO()
    configure_logger = svc.predict.__func__.__globals__["_configure_production_logger"]
    configure_logger(output)

    try:
        with patch.dict(svc.predict.__func__.__globals__, {"logger": real_logger}):
            response = asyncio.run(svc.predict(["safe input"]))
    finally:
        configure_logger()

    assert response.success is False
    assert response.error.code == "E2001"
    assert secret in response.error.message
    safe_exception_info = svc.predict.__func__.__globals__["_safe_exception_info"]
    safe_type, safe_error, safe_traceback = safe_exception_info(error)
    assert safe_traceback is error.__traceback__
    assert safe_error is not error
    assert safe_type.__name__ == "_SafeLogException"
    assert isinstance(safe_error, RuntimeError)
    assert str(safe_error) == "RuntimeError"
    assert str(error) == secret
    rendered = output.getvalue()
    assert "event=text_classification_failed failed_stage=model_predict error_type=RuntimeError" in rendered
    assert "call_chain=" in rendered
    assert "Traceback" in rendered
    assert "service.py" in rendered
    assert secret not in rendered
    assert frame_secret not in rendered
