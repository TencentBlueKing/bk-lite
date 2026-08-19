from types import SimpleNamespace

import pytest
import requests

from apps.cmdb.services.stargazer_collect_trigger import StargazerCollectPermanentError, StargazerCollectRetryableError, StargazerCollectTriggerClient


def _response(status_code, headers):
    return SimpleNamespace(status_code=status_code, headers=headers, text="")


def test_admit_accepts_202_with_target_count(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: _response(
            202,
            {"X-Task-Status": "accepted", "X-Target-Count": "12", "X-Task-ID": "req_abc"},
        ),
    )
    result = StargazerCollectTriggerClient().admit({"cmdbplugin_name": "mysql_info"})
    assert result.status == "accepted"
    assert result.total == 12
    assert result.accepted == 12


def test_admit_treats_duplicate_active_as_success(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: _response(
            202,
            {"X-Task-Status": "duplicate_active", "X-Target-Count": "8"},
        ),
    )
    result = StargazerCollectTriggerClient().admit({"cmdbhosts": "10.0.1.1"})
    assert result.status == "duplicate"
    assert result.total == 8


def test_admit_429_is_retryable(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: _response(429, {"X-Task-Status": "busy", "Retry-After": "1"}),
    )
    with pytest.raises(StargazerCollectRetryableError):
        StargazerCollectTriggerClient().admit({"cmdbplugin_name": "mysql_info"})


def test_admit_rejects_legacy_200_queued(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: _response(200, {"X-Task-Status": "queued"}),
    )
    with pytest.raises(StargazerCollectPermanentError):
        StargazerCollectTriggerClient().admit({"cmdbplugin_name": "mysql_info"})
