import pytest

from apps.operation_analysis.services.datasource_preview.base import ConnectorError
from apps.operation_analysis.services.datasource_preview.rest_api import (
    MAX_TRANSFORM_ROWS,
    RestApiConnectorExecutor,
    maybe_apply_transform,
)
from apps.operation_analysis.services.transform.errors import TransformError
from apps.operation_analysis.services.transform.executor import TransformExecutor


def test_maybe_apply_transform_skips_when_disabled():
    rows = [{"a": 1}]
    assert maybe_apply_transform(rows, {"enabled": False, "script": "x"}) == rows


def test_maybe_apply_transform_requires_runner_when_enabled():
    class Boom:
        def execute(self, *args, **kwargs):
            raise TransformError("转换服务不可用", code="transform_runner_unavailable", status_code=503)

    with pytest.raises(ConnectorError) as exc:
        maybe_apply_transform(
            [{"a": 1}],
            {"enabled": True, "language": "python", "script": "def transform(rows, params):\n  return rows"},
            transform_executor=Boom(),
        )
    assert exc.value.code == "transform_runner_unavailable"


def test_rest_preview_transforms_before_sampling():
    class FakeResponse:
        headers = {"content-length": "128"}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            yield b'[{"n":1},{"n":2},{"n":3}]'

        def close(self):
            return None

    class FakeClient:
        def request(self, **kwargs):
            return FakeResponse()

    class FakeTransform:
        def execute(self, rows, params, script, **kwargs):
            assert len(rows) == 3
            assert params == {}
            assert "transform" in script
            return [{"n": row["n"] * 10} for row in rows]

    result = RestApiConnectorExecutor(
        http_client=FakeClient(),
        transform_executor=FakeTransform(),
    ).preview(
        {"url": "https://example.com/items", "method": "GET"},
        {},
        limit=1,
        transform_config={
            "enabled": True,
            "language": "python",
            "script": "def transform(rows, params):\n    return rows",
        },
    )
    assert result.items == [{"n": 10}]
    assert result.count == 3
    assert result.raw_items == [{"n": 1}]
    assert result.raw_count == 3
    assert result.transform_error is None


def test_rest_preview_transform_failure_keeps_raw_sample():
    class FakeResponse:
        headers = {"content-length": "64"}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            yield b'[{"n":1},{"n":2}]'

        def close(self):
            return None

    class FakeClient:
        calls = 0

        def request(self, **kwargs):
            FakeClient.calls += 1
            return FakeResponse()

    class FakeTransform:
        def execute(self, rows, params, script, **kwargs):
            raise TransformError("boom", code="transform_failed", status_code=400)

    FakeClient.calls = 0
    result = RestApiConnectorExecutor(
        http_client=FakeClient(),
        transform_executor=FakeTransform(),
    ).preview(
        {"url": "https://example.com/items", "method": "GET"},
        {},
        limit=10,
        transform_config={
            "enabled": True,
            "language": "python",
            "script": "def transform(rows, params):\n    return rows",
        },
    )
    assert FakeClient.calls == 1
    assert result.raw_items == [{"n": 1}, {"n": 2}]
    assert result.transform_error["code"] == "transform_failed"
    assert result.items == [{"n": 1}, {"n": 2}]


def test_rest_preview_rejects_more_than_max_rows_before_transform():
    payload = "[" + ",".join(['{"n":%d}' % i for i in range(MAX_TRANSFORM_ROWS + 1)]) + "]"

    class FakeResponse:
        headers = {}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            yield payload.encode("utf-8")

        def close(self):
            return None

    class FakeClient:
        def request(self, **kwargs):
            return FakeResponse()

    class FakeTransform:
        def execute(self, *args, **kwargs):
            raise AssertionError("should not transform oversized input")

    with pytest.raises(ConnectorError) as exc:
        RestApiConnectorExecutor(
            http_client=FakeClient(),
            transform_executor=FakeTransform(),
        ).preview({"url": "https://example.com/big"}, {}, limit=10)

    assert exc.value.code == "rest_rows_too_many"


def test_transform_executor_maps_capacity_error():
    class FakeResponse:
        status_code = 429
        content = b'{"result":false,"code":"transform_capacity_exceeded","message":"busy"}'

        def json(self):
            return {
                "result": False,
                "code": "transform_capacity_exceeded",
                "message": "busy",
            }

    def fake_request(method, url, **kwargs):
        return FakeResponse()

    executor = TransformExecutor(base_url="http://runner", request_func=fake_request, token="secret")
    with pytest.raises(TransformError) as exc:
        executor.execute([{"a": 1}], {}, "def transform(rows, params):\n return rows")
    assert exc.value.code == "transform_capacity_exceeded"
    assert exc.value.status_code == 429


def test_transform_executor_unavailable_without_url():
    executor = TransformExecutor(base_url="", token="secret")
    with pytest.raises(TransformError) as exc:
        executor.execute([], {}, "def transform(rows, params):\n return rows")
    assert exc.value.code == "transform_runner_unavailable"


def test_transform_executor_requires_token():
    executor = TransformExecutor(base_url="http://runner", token="")
    with pytest.raises(TransformError) as exc:
        executor.execute([], {}, "def transform(rows, params):\n return rows")
    assert exc.value.code == "transform_runner_misconfigured"
