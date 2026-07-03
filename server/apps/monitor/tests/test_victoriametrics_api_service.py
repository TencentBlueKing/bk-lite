"""VictoriaMetricsAPI 测试 — mock requests 边界,校验 URL/params/auth 入参与异常透传。"""
from unittest.mock import MagicMock, patch

import pytest
import requests

from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI

pytestmark = pytest.mark.unit


def _resp(payload):
    r = MagicMock()
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


def test_query_builds_path_and_params():
    api = VictoriaMetricsAPI()
    with patch("apps.monitor.utils.victoriametrics_api.requests.get", return_value=_resp({"ok": 1})) as g:
        out = api.query("cpu", step="1m", time=12345)
    assert out == {"ok": 1}
    args, kwargs = g.call_args
    assert args[0].endswith("/api/v1/query")
    assert kwargs["params"] == {"query": "cpu", "step": "1m", "time": 12345}
    assert kwargs["auth"] == (api.username, api.password)


def test_query_omits_empty_step_and_time():
    api = VictoriaMetricsAPI()
    with patch("apps.monitor.utils.victoriametrics_api.requests.get", return_value=_resp({})) as g:
        api.query("cpu", step=None, time=None)
    assert g.call_args.kwargs["params"] == {"query": "cpu"}


def test_query_range_builds_params():
    api = VictoriaMetricsAPI()
    with patch("apps.monitor.utils.victoriametrics_api.requests.get", return_value=_resp({"r": []})) as g:
        out = api.query_range("cpu", "s", "e", step="30s")
    assert out == {"r": []}
    args, kwargs = g.call_args
    assert args[0].endswith("/api/v1/query_range")
    assert kwargs["params"] == {"query": "cpu", "start": "s", "end": "e", "step": "30s"}


def test_timeout_is_propagated():
    api = VictoriaMetricsAPI()
    with patch("apps.monitor.utils.victoriametrics_api.requests.get", side_effect=requests.Timeout("boom")):
        with pytest.raises(requests.Timeout):
            api.query("cpu")


def test_request_exception_is_propagated():
    api = VictoriaMetricsAPI()
    with patch("apps.monitor.utils.victoriametrics_api.requests.get", side_effect=requests.ConnectionError("x")):
        with pytest.raises(requests.RequestException):
            api.query_range("cpu", "s", "e")


def test_http_error_raised_via_raise_for_status():
    api = VictoriaMetricsAPI()
    r = MagicMock()
    r.raise_for_status.side_effect = requests.HTTPError("500")
    with patch("apps.monitor.utils.victoriametrics_api.requests.get", return_value=r):
        with pytest.raises(requests.HTTPError):
            api.query("cpu")
