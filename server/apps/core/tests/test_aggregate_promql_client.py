from datetime import UTC, datetime

import pytest

from apps.core.aggregate_promql import AggregateMetricsTooLarge, AggregateMetricsUnavailable, AggregatePromqlClient, escape_promql_label_value

AT = datetime(2026, 11, 10, 0, 15, tzinfo=UTC)
SUCCESS = b'{"status":"success","data":{"resultType":"vector","result":[{"metric":{},"value":[1,"2"]}]}}'


def _sentinel(kind: str) -> str:
    return "-".join(["AGG", kind, "SENTINEL"])


class _Response:
    def __init__(self, *, status_code=200, headers=None, chunks=None):
        self.status_code = status_code
        self.headers = {} if headers is None else headers
        self._chunks = SUCCESS if chunks is None else chunks
        self.closed = False

    def iter_content(self, chunk_size=65536):
        if isinstance(self._chunks, list):
            yield from self._chunks
            return
        yield self._chunks

    def close(self):
        self.closed = True


class _Session:
    def __init__(self, response=None):
        self.response = response or _Response()
        self.calls = []
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response

    def close(self):
        self.closed = True


def _client(monkeypatch, session, **env):
    monkeypatch.delenv("AGG_VICTORIAMETRICS_QUERY_URL", raising=False)
    monkeypatch.delenv("AGG_VICTORIAMETRICS_USER", raising=False)
    monkeypatch.delenv("AGG_VICTORIAMETRICS_PASSWORD", raising=False)
    monkeypatch.setenv("VICTORIAMETRICS_HOST", "http://monitor.example:8428")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return AggregatePromqlClient.from_env(session=session)


def test_unconfigured_client_does_not_use_monitor_host_or_open_a_session(monkeypatch):
    monkeypatch.delenv("AGG_VICTORIAMETRICS_QUERY_URL", raising=False)
    monkeypatch.setenv("VICTORIAMETRICS_HOST", "http://monitor.example:8428")
    monkeypatch.setattr(
        "apps.core.aggregate_promql.requests.Session",
        lambda: (_ for _ in ()).throw(AssertionError("opened session")),
    )

    client = AggregatePromqlClient.from_env()

    assert client.available is False
    with pytest.raises(AggregateMetricsUnavailable, match="^unconfigured$"):
        client.query_instant("up", at=AT)


def test_instant_and_range_use_aggregate_url_timeout_and_auth(monkeypatch):
    session = _Session()
    client = _client(
        monkeypatch,
        session,
        AGG_VICTORIAMETRICS_QUERY_URL="http://aggregate.test/api/v1/",
        AGG_VICTORIAMETRICS_USER="agg-user",
        AGG_VICTORIAMETRICS_PASSWORD=_sentinel("PASSWORD"),
    )

    instant = client.query_instant('sum(up{job="x"})', at=AT)
    ranged = client.query_range(
        "up",
        start=AT,
        end=datetime(2026, 11, 10, 0, 16, tzinfo=UTC),
        step_seconds=15,
    )

    assert instant == [{"metric": {}, "value": [1, "2"]}]
    assert ranged == [{"metric": {}, "value": [1, "2"]}]
    assert [url for url, _ in session.calls] == [
        "http://aggregate.test/api/v1/query",
        "http://aggregate.test/api/v1/query_range",
    ]
    instant_kwargs = session.calls[0][1]
    assert instant_kwargs["timeout"] == (3.0, 10.0)
    assert instant_kwargs["auth"] == ("agg-user", _sentinel("PASSWORD"))
    assert instant_kwargs["allow_redirects"] is False
    assert instant_kwargs["params"]["query"] == 'sum(up{job="x"})'
    assert instant_kwargs["params"]["time"] == "1794269700.000"
    assert session.calls[1][1]["params"]["step"] == "15"
    assert _sentinel("PASSWORD") not in session.calls[0][0]
    assert "monitor.example" not in session.calls[0][0]


@pytest.mark.parametrize(
    "base_url",
    [
        "http://aggregate.test",
        "http://aggregate.test/api/v1",
        "http://aggregate.test/api/v1/query",
        "http://aggregate.test/api/v1/query_range",
    ],
)
def test_query_url_accepts_base_or_api_suffix(monkeypatch, base_url):
    session = _Session()
    client = _client(monkeypatch, session, AGG_VICTORIAMETRICS_QUERY_URL=base_url)

    client.query_instant("up", at=AT)

    assert session.calls[0][0] == "http://aggregate.test/api/v1/query"


def test_partial_credentials_are_unavailable_and_do_not_send_the_password(monkeypatch):
    session = _Session()
    client = _client(
        monkeypatch,
        session,
        AGG_VICTORIAMETRICS_QUERY_URL="http://aggregate.test",
        AGG_VICTORIAMETRICS_PASSWORD=_sentinel("PASSWORD"),
    )

    assert client.available is False
    with pytest.raises(AggregateMetricsUnavailable, match="^unconfigured$"):
        client.query_instant("up", at=AT)
    assert session.calls == []


def test_url_userinfo_is_unavailable(monkeypatch):
    session = _Session()
    monkeypatch.setenv("VICTORIAMETRICS_HOST", "http://monitor.example:8428")
    client = AggregatePromqlClient(
        base_url="http://agg-user:" + _sentinel("PASSWORD") + "@aggregate.test",
        session=session,
    )

    assert client.available is False
    with pytest.raises(AggregateMetricsUnavailable, match="^unconfigured$"):
        client.query_instant("up", at=AT)
    assert session.calls == []


def test_http_error_message_omits_the_response_body(monkeypatch):
    body = _sentinel("BODY").encode()
    session = _Session(_Response(status_code=500, chunks=body))
    client = _client(monkeypatch, session, AGG_VICTORIAMETRICS_QUERY_URL="http://aggregate.test")

    with pytest.raises(AggregateMetricsUnavailable, match="^http$") as caught:
        client.query_instant("up", at=AT)

    assert _sentinel("BODY") not in str(caught.value)
    assert session.response.closed is True


def test_redirect_is_not_followed(monkeypatch):
    session = _Session(_Response(status_code=302, chunks=b"next"))
    client = _client(monkeypatch, session, AGG_VICTORIAMETRICS_QUERY_URL="http://aggregate.test")

    with pytest.raises(AggregateMetricsUnavailable, match="^http$"):
        client.query_instant("up", at=AT)

    assert len(session.calls) == 1
    assert session.calls[0][1]["allow_redirects"] is False


def test_content_length_over_the_limit_raises_before_reading_the_body(monkeypatch):
    class _Unread(_Response):
        def iter_content(self, chunk_size=65536):
            raise AssertionError("body read")

    session = _Session(_Unread(headers={"Content-Length": str(2 * 1024 * 1024 + 1)}))
    client = _client(monkeypatch, session, AGG_VICTORIAMETRICS_QUERY_URL="http://aggregate.test")

    with pytest.raises(AggregateMetricsTooLarge, match="^too_large$") as caught:
        client.query_instant("up", at=AT)

    assert _sentinel("BODY") not in str(caught.value)


def test_streamed_body_over_the_limit_omits_the_payload(monkeypatch):
    token = _sentinel("BODY").encode()
    blob = token * ((2 * 1024 * 1024) // len(token) + 2)
    session = _Session(_Response(headers={}, chunks=blob))
    client = _client(monkeypatch, session, AGG_VICTORIAMETRICS_QUERY_URL="http://aggregate.test")

    with pytest.raises(AggregateMetricsTooLarge, match="^too_large$") as caught:
        client.query_instant("up", at=AT)

    assert token.decode() not in str(caught.value)


def test_label_values_escape_quotes_backslashes_and_newlines():
    assert escape_promql_label_value('a"b\\c') == 'a\\"b\\\\c'
    assert escape_promql_label_value("line\nnext") == "line\\nnext"
