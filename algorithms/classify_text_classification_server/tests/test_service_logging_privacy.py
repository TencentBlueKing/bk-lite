"""Regression tests for predict debug logging privacy (Issue #3853)."""

import asyncio
from unittest.mock import MagicMock

import pandas as pd

from tests.test_feature_importance import _load_service_module, _make_service


def test_predict_debug_logs_do_not_include_request_texts():
    """predict() should log metadata only, never raw or processed request text."""
    service_mod = _load_service_module()
    logger = service_mod.logger
    logger.reset_mock()

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
    assert "Preprocessed text summary" in debug_output
    assert "Calling model.predict with text summary" in debug_output
    assert "'count': 2" in debug_output
    assert "'truncated_count': 1" in debug_output
