from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from loguru import logger as real_logger


def _make_service(service_module, model):
    service_class = getattr(service_module.MLService, "inner", service_module.MLService)
    instance = object.__new__(service_class)
    instance.config = SimpleNamespace(source="dummy", mlflow_model_uri=None)
    instance.model = model
    return instance


def test_serving_lifecycle_uses_stable_non_decorative_events(monkeypatch):
    from classify_anomaly_server.serving import service

    logger = MagicMock()
    monkeypatch.setattr(service, "logger", logger)
    service_class = getattr(service.MLService, "inner", service.MLService)

    service_class.setup()
    service_class.cleanup(object.__new__(service_class))

    assert logger.info.call_args_list == [
        (("event=anomaly_service_deployment_setup_completed",), {}),
        (("event=anomaly_service_cleanup_completed",), {}),
    ]
    assert "===" not in repr(logger.mock_calls)


@pytest.mark.asyncio
async def test_predict_success_preserves_response_with_stable_terminal_log(monkeypatch):
    from classify_anomaly_server.serving import service

    logger = MagicMock()
    monkeypatch.setattr(service, "logger", logger)
    model = MagicMock()
    model.predict.return_value = {
        "labels": [0, 0, 1, 0, 0],
        "scores": [0.1, 0.2, 0.9, 0.2, 0.1],
        "anomaly_severity": [0.1, 0.2, 0.9, 0.2, 0.1],
    }
    instance = _make_service(service, model)
    data = [{"timestamp": 1700000000 + index * 60, "value": float(index)} for index in range(5)]

    response = await instance.predict(data)

    assert response.success is True
    assert len(response.results) == len(data)
    assert any(call.args[0].startswith("event=anomaly_detection_completed") for call in logger.info.call_args_list)
    assert "📥" not in repr(logger.mock_calls)


@pytest.mark.asyncio
async def test_predict_failure_preserves_error_response_and_single_sanitized_traceback(monkeypatch):
    from classify_anomaly_server.serving import service

    secret = "model-response-secret-must-not-enter-logs"
    frame_secret = "frame-local-secret-must-not-enter-logs"
    monkeypatch.setattr(service, "logger", real_logger)
    model = MagicMock()
    error = RuntimeError(secret)
    def fail_with_sensitive_local(*_args, **_kwargs):
        sensitive_local = frame_secret
        assert sensitive_local
        raise error

    model.predict.side_effect = fail_with_sensitive_local
    output = StringIO()
    service._configure_production_logger(output)
    instance = _make_service(service, model)
    data = [{"timestamp": 1700000000 + index * 60, "value": float(index)} for index in range(5)]

    try:
        response = await instance.predict(data)
    finally:
        service._configure_production_logger()

    assert response.success is False
    assert response.error.code == "E2002"
    assert secret in response.error.message
    safe_type, safe_error, safe_traceback = service._safe_exception_info(error)
    assert safe_traceback is error.__traceback__
    assert safe_error is not error
    assert safe_type.__name__ == "_SafeLogException"
    assert isinstance(safe_error, RuntimeError)
    assert str(safe_error) == "RuntimeError"
    assert str(error) == secret
    rendered = output.getvalue()
    assert "event=anomaly_detection_failed failed_stage=model_predict error_type=RuntimeError" in rendered
    assert "call_chain=" in rendered
    assert "Traceback" in rendered
    assert "service.py" in rendered
    assert secret not in rendered
    assert frame_secret not in rendered
