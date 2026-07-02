import pydantic.root_model  # noqa

import pytest

from apps.log.utils.query_log import VictoriaMetricsAPI


# ----------------------- _normalize_logsql_query -----------------------


def test_normalize_logsql_query_none_and_blank():
    assert VictoriaMetricsAPI._normalize_logsql_query(None) == ""
    assert VictoriaMetricsAPI._normalize_logsql_query("   ") == ""


def test_normalize_logsql_query_plain_string_is_stripped():
    assert VictoriaMetricsAPI._normalize_logsql_query("  level:error  ") == "level:error"


def test_normalize_logsql_query_unwraps_single_json_encoded_string():
    # 一层 JSON 编码的字符串应被解码
    assert VictoriaMetricsAPI._normalize_logsql_query('"level:error"') == "level:error"


def test_normalize_logsql_query_unwraps_double_json_encoded_string():
    # 两层 JSON 编码：'"\\"x\\""' -> '"x"' -> 'x'
    import json

    double = json.dumps(json.dumps("host:web-1"))
    assert VictoriaMetricsAPI._normalize_logsql_query(double) == "host:web-1"


def test_normalize_logsql_query_stops_on_non_string_json():
    # JSON 解出非字符串（数字）时保留原文本
    assert VictoriaMetricsAPI._normalize_logsql_query("123") == "123"


def test_normalize_logsql_query_breaks_when_decoded_equals_current():
    # 解码后与当前值相同则停止循环
    assert VictoriaMetricsAPI._normalize_logsql_query('""') == ""


# ----------------------- _build_url -----------------------


def test_build_url_joins_host_and_path_trimming_slash():
    url = VictoriaMetricsAPI._build_url("http://vm:9428/", "/select/logsql/query")
    assert url == "http://vm:9428/select/logsql/query"


def test_build_url_raises_on_empty_host():
    with pytest.raises(ValueError, match="not configured"):
        VictoriaMetricsAPI._build_url("", "/x")
    with pytest.raises(ValueError):
        VictoriaMetricsAPI._build_url(None, "/x")


# ----------------------- _extract_metric_value -----------------------


METRICS_SAMPLE = """\
# HELP vl_data_size_bytes data size
# TYPE vl_data_size_bytes gauge
vl_data_size_bytes{type="storage"} 1073741824
vl_data_size_bytes{type="indexdb"} 536870912
other_metric{type="storage"} 5
"""


def test_extract_metric_value_matches_name_and_type():
    assert VictoriaMetricsAPI._extract_metric_value(METRICS_SAMPLE, "vl_data_size_bytes", "storage") == 1073741824
    assert VictoriaMetricsAPI._extract_metric_value(METRICS_SAMPLE, "vl_data_size_bytes", "indexdb") == 536870912


def test_extract_metric_value_raises_when_not_found():
    with pytest.raises(ValueError, match="未找到指标"):
        VictoriaMetricsAPI._extract_metric_value(METRICS_SAMPLE, "vl_data_size_bytes", "missing")


def test_extract_metric_value_raises_on_non_integer_value():
    text = 'vl_data_size_bytes{type="storage"} 1.5\n'
    with pytest.raises(ValueError, match="不是整数"):
        VictoriaMetricsAPI._extract_metric_value(text, "vl_data_size_bytes", "storage")


def test_extract_metric_value_raises_on_illegal_value():
    text = 'vl_data_size_bytes{type="storage"} notanumber\n'
    with pytest.raises(ValueError, match="非法"):
        VictoriaMetricsAPI._extract_metric_value(text, "vl_data_size_bytes", "storage")


def test_extract_metric_value_integral_decimal_accepted():
    text = 'vl_data_size_bytes{type="storage"} 100.0\n'
    assert VictoriaMetricsAPI._extract_metric_value(text, "vl_data_size_bytes", "storage") == 100


# ----------------------- _build_auth -----------------------


def test_build_auth_none_when_no_credentials(mocker):
    mocker.patch("apps.log.utils.query_log.VictoriaLogsConstants.USER", "")
    mocker.patch("apps.log.utils.query_log.VictoriaLogsConstants.PWD", "")
    api = VictoriaMetricsAPI()
    assert api.auth is None


def test_build_auth_basic_auth_when_credentials(mocker):
    mocker.patch("apps.log.utils.query_log.VictoriaLogsConstants.USER", "u")
    mocker.patch("apps.log.utils.query_log.VictoriaLogsConstants.PWD", "p")
    api = VictoriaMetricsAPI()
    assert api.auth is not None
    assert api.auth.username == "u"
    assert api.auth.password == "p"


# ----------------------- query() parsing -----------------------


class _FakeResponse:
    def __init__(self, lines, text="", json_data=None):
        self._lines = lines
        self.text = text
        self._json = json_data
        self.status_code = 200

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=True):
        return iter(self._lines)

    def json(self):
        return self._json


def _api(mocker):
    mocker.patch("apps.log.utils.query_log.VictoriaLogsConstants.HOST", "http://vm:9428")
    mocker.patch("apps.log.utils.query_log.VictoriaLogsConstants.USER", "")
    mocker.patch("apps.log.utils.query_log.VictoriaLogsConstants.PWD", "")
    return VictoriaMetricsAPI()


def test_query_parses_valid_lines_and_skips_blank(mocker):
    api = _api(mocker)
    resp = _FakeResponse(['{"a": 1}', "", '{"b": 2}'])
    post = mocker.patch("apps.log.utils.query_log.requests.post", return_value=resp)
    result = api.query("level:error", "s", "e", 5)
    assert result == [{"a": 1}, {"b": 2}]
    # 校验请求契约：URL/params/auth/verify/timeout
    args, kwargs = post.call_args
    assert args[0] == "http://vm:9428/select/logsql/query"
    assert kwargs["params"] == {"query": "level:error", "start": "s", "end": "e", "limit": 5}
    assert kwargs["timeout"] == VictoriaMetricsAPI.REQUEST_TIMEOUT


def test_query_clamps_limit_above_max(mocker):
    api = _api(mocker)
    resp = _FakeResponse([])
    post = mocker.patch("apps.log.utils.query_log.requests.post", return_value=resp)
    api.query("q", "s", "e", limit=10 ** 9)
    assert post.call_args.kwargs["params"]["limit"] == 1000  # QUERY_LIMIT_MAX


# ----------------------- all_field_names / field_values / hits -----------------------


def test_all_field_names_returns_response_json(mocker):
    api = _api(mocker)
    resp = _FakeResponse([], json_data={"values": [{"value": "host"}]})
    get = mocker.patch("apps.log.utils.query_log.requests.get", return_value=resp)
    out = api.all_field_names("level:error", "s", "e")
    assert out == {"values": [{"value": "host"}]}
    assert get.call_args.args[0] == "http://vm:9428/select/logsql/field_names"
    assert get.call_args.kwargs["params"]["ignore_pipes"] == 1


def test_all_field_names_uses_wildcard_when_query_empty(mocker):
    api = _api(mocker)
    resp = _FakeResponse([], json_data={})
    get = mocker.patch("apps.log.utils.query_log.requests.get", return_value=resp)
    api.all_field_names("", "s", "e")
    assert get.call_args.kwargs["params"]["query"] == "*"


def test_field_values_builds_default_query_and_limit(mocker):
    api = _api(mocker)
    resp = _FakeResponse([], json_data={"values": []})
    get = mocker.patch("apps.log.utils.query_log.requests.get", return_value=resp)
    api.field_values("s", "e", "host", limit=50, query=None)
    params = get.call_args.kwargs["params"]
    assert params["query"] == "host:*"
    assert params["field"] == "host"
    assert params["limit"] == 50


def test_hits_aggregates_response_json(mocker):
    api = _api(mocker)
    resp = _FakeResponse([], json_data={"hits": []})
    post = mocker.patch("apps.log.utils.query_log.requests.post", return_value=resp)
    out = api.hits("q", "s", "e", "host", fields_limit=3, step="1m")
    assert out == {"hits": []}
    assert post.call_args.args[0] == "http://vm:9428/select/logsql/hits"
    assert post.call_args.kwargs["params"]["step"] == "1m"


# ----------------------- get_disk_usage -----------------------


def test_get_disk_usage_sums_storage_and_indexdb(mocker):
    api = _api(mocker)
    resp = _FakeResponse([], text=METRICS_SAMPLE)
    mocker.patch("apps.log.utils.query_log.requests.get", return_value=resp)
    out = api.get_disk_usage()
    assert out["storage_bytes"] == 1073741824
    assert out["indexdb_bytes"] == 536870912
    assert out["used_bytes"] == 1073741824 + 536870912
    assert out["unit"] == "GB"
    assert out["used_gb"] == round((1073741824 + 536870912) / (1024 ** 3), 2)


def test_get_disk_usage_raises_on_request_error(mocker):
    import requests as real_requests

    api = _api(mocker)
    mocker.patch(
        "apps.log.utils.query_log.requests.get",
        side_effect=real_requests.RequestException("boom"),
    )
    with pytest.raises(real_requests.RequestException):
        api.get_disk_usage()


def test_get_disk_usage_raises_on_metric_parse_error(mocker):
    api = _api(mocker)
    resp = _FakeResponse([], text="# nothing useful\n")
    mocker.patch("apps.log.utils.query_log.requests.get", return_value=resp)
    with pytest.raises(ValueError):
        api.get_disk_usage()
