from unittest.mock import MagicMock


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
