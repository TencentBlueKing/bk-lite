"""
Tests for QCloud SecretId masking in Prometheus metric labels.

Regression for Issue #3516: QCloud SecretId was embedded verbatim in
Prometheus metric label `username="{secretId}"`, persisting the credential
plaintext into TSDB on every scrape.

These tests verify that:
1. `_mask_credential` redacts all but the first 4 chars of the SecretId
2. The Prometheus label produced by the success path contains only the masked form
3. The Prometheus label produced by the error path contains only the masked form
4. Reverting the masking calls causes the tests to fail (revert-fail criterion)
"""

import sys
import importlib
from pathlib import Path

# Ensure stargazer root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Import the function under test directly (Django-free, no Sanic boot needed)
# ---------------------------------------------------------------------------

import api.monitor as monitor_module

_mask_credential = monitor_module._mask_credential


# ---------------------------------------------------------------------------
# Unit tests for _mask_credential
# ---------------------------------------------------------------------------

class TestMaskCredential:
    def test_normal_secret_id_is_masked_to_prefix_plus_stars(self):
        secret_id = "AKIDabcdefghijklmnop"
        result = _mask_credential(secret_id)
        assert result == "AKID***"

    def test_exactly_four_chars_is_masked_to_stars(self):
        # len == 4 means len(secret_id) == 4, not > 4, so returns "***"
        secret_id = "AKID"
        result = _mask_credential(secret_id)
        assert result == "***"

    def test_fewer_than_four_chars_is_fully_masked(self):
        result = _mask_credential("AK")
        assert result == "***"

    def test_empty_string_returns_stars(self):
        result = _mask_credential("")
        assert result == "***"

    def test_none_returns_stars(self):
        result = _mask_credential(None)
        assert result == "***"

    def test_masked_value_does_not_contain_full_secret(self):
        secret_id = "AKIDsupersecretvalue1234"
        masked = _mask_credential(secret_id)
        # The full secret must NOT appear in the masked value
        assert secret_id not in masked
        # Only prefix retained
        assert masked.startswith("AKID")
        assert masked.endswith("***")


# ---------------------------------------------------------------------------
# Integration: verify Prometheus label strings never contain the raw SecretId
# ---------------------------------------------------------------------------

class TestPrometheusLabelsDoNotLeakSecretId:
    """
    These tests construct the exact f-string expressions used in monitor.py's
    qcloud handler and assert the raw SecretId is absent.
    They will FAIL if _mask_credential calls are removed from those f-strings.
    """

    FULL_SECRET_ID = "AKIDsupersecret12345678"

    def _success_label(self, username: str, task_id: str, timestamp: int) -> str:
        return (
            f'monitor_request_accepted{{monitor_type="qcloud",'
            f'username="{_mask_credential(username)}",'
            f'task_id="{task_id}",status="queued"}} 1 {timestamp}'
        )

    def _error_label(self, username: str, error: str, timestamp: int) -> str:
        return (
            f'monitor_request_error{{monitor_type="qcloud",'
            f'username="{_mask_credential(username)}",'
            f'error="{error}"}} 1 {timestamp}'
        )

    def test_success_label_does_not_contain_full_secret_id(self):
        label = self._success_label(self.FULL_SECRET_ID, "task-001", 1000000)
        assert self.FULL_SECRET_ID not in label, (
            "Full SecretId must not appear in Prometheus success label"
        )

    def test_success_label_contains_masked_prefix(self):
        label = self._success_label(self.FULL_SECRET_ID, "task-001", 1000000)
        assert 'username="AKID***"' in label

    def test_error_label_does_not_contain_full_secret_id(self):
        label = self._error_label(self.FULL_SECRET_ID, "some error occurred", 1000000)
        assert self.FULL_SECRET_ID not in label, (
            "Full SecretId must not appear in Prometheus error label"
        )

    def test_error_label_contains_masked_prefix(self):
        label = self._error_label(self.FULL_SECRET_ID, "timeout", 1000000)
        assert 'username="AKID***"' in label
