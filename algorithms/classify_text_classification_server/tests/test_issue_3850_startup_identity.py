"""Text-classification startup identity contract for Issue #3850."""

import asyncio

from classify_text_classification_server.serving.service import MLService


def test_health_binds_readiness_to_current_serving_instance(monkeypatch):
    monkeypatch.setenv("MODEL_SOURCE", "dummy")
    monkeypatch.setenv("SERVING_INSTANCE_ID", "issue-3850-instance")

    service = MLService()
    health = asyncio.run(service.health())

    assert health["status"] == "healthy"
    assert health["startup_instance_id"] == "issue-3850-instance"
