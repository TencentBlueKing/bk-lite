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
    with patch("apps.monitor.utils.victoriametrics_api._SESSION.get", return_value=_resp({"ok": 1})) as g:
        out = api.query("cpu", step="1m", time=12345)
    assert out == {"ok": 1}
    args, kwargs = g.call_args
    assert args[0].endswith("/api/v1/query")
    assert kwargs["params"] == {"query": "cpu", "step": "1m", "time": 12345}
    assert kwargs["auth"] == (api.username, api.password)


def test_query_omits_empty_step_and_time():
    api = VictoriaMetricsAPI()
    with patch("apps.monitor.utils.victoriametrics_api._SESSION.get", return_value=_resp({})) as g:
        api.query("cpu", step=None, time=None)
    assert g.call_args.kwargs["params"] == {"query": "cpu"}


def test_query_includes_lookback_delta_when_supplied():
    api = VictoriaMetricsAPI()
    with patch("apps.monitor.utils.victoriametrics_api._SESSION.get", return_value=_resp({})) as g:
        api.query("cpu", lookback_delta="600s")
    assert g.call_args.kwargs["params"] == {"query": "cpu", "step": "5m", "lookback_delta": "600s"}


def test_query_range_posts_form_params():
    """范围下推后 selector 可能很长，query_range 必须走 form POST 而不是 GET 查询串。"""
    api = VictoriaMetricsAPI()
    with patch("apps.monitor.utils.victoriametrics_api._SESSION.post", return_value=_resp({"r": []})) as p, patch(
        "apps.monitor.utils.victoriametrics_api._SESSION.get"
    ) as g:
        out = api.query_range("cpu", "s", "e", step="30s")
    assert out == {"r": []}
    g.assert_not_called()
    args, kwargs = p.call_args
    assert args[0].endswith("/api/v1/query_range")
    assert kwargs["data"] == {"query": "cpu", "start": "s", "end": "e", "step": "30s"}
    assert "params" not in kwargs
    assert kwargs["auth"] == (api.username, api.password)


def test_timeout_is_propagated():
    api = VictoriaMetricsAPI()
    with patch("apps.monitor.utils.victoriametrics_api._SESSION.get", side_effect=requests.Timeout("boom")):
        with pytest.raises(requests.Timeout):
            api.query("cpu")


def test_request_exception_is_propagated():
    api = VictoriaMetricsAPI()
    with patch("apps.monitor.utils.victoriametrics_api._SESSION.post", side_effect=requests.ConnectionError("x")):
        with pytest.raises(requests.RequestException):
            api.query_range("cpu", "s", "e")


def test_http_error_raised_via_raise_for_status():
    api = VictoriaMetricsAPI()
    r = MagicMock()
    r.raise_for_status.side_effect = requests.HTTPError("500")
    with patch("apps.monitor.utils.victoriametrics_api._SESSION.get", return_value=r):
        with pytest.raises(requests.HTTPError):
            api.query("cpu")
