# -*- coding: utf-8 -*-
"""
Unit tests for :class:`apps.operation_analysis.services.network_topology.weops_adapter`.

Coverage targets:

* ``x-token`` + ``x-bklite-trace-id`` headers injection.
* Response unwrapping: ``{"result": True, "data": <payload>}`` →
  ``<payload>``.
* Endpoints: URL building (``node_ref`` URL encoding in particular) and
  method/payload handling for all 8 WeOps endpoints.
* ``all=true`` is forced for ``list_nodes`` (design.md §5.4).
* Item-level ``error_code`` is mapped onto the internal enum; unknowns
  fall back to ``UNKNOWN``.
* HTTP 401/403 ⇒ ``weops_token_invalid`` (design.md §5.3, §10.2).
* Retry on transient transport errors.
* ``test_connection`` surface-level success / failure.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

import pytest

from apps.operation_analysis.services.network_topology.weops_adapter import (
    WEOPS_TOKEN_INVALID,
    NetworkTopologyErrorType,
    WeOpsTopologyAdapter,
    WeOpsTopologyAdapterError,
    encode_node_ref,
    map_item_error_code,
)

# --------------------------------------------------------------------------- #
# Fake HTTP client                                                              #
# --------------------------------------------------------------------------- #


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeHttpClient:
    """Mimics ``requests`` interface enough for the adapter."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        raise AssertionError("FakeHttpClient ran out of responses")


def _adapter(responses=None, token="service-token", http_client=None, retry=1, timeout=10, trace_id_factory=None):
    return WeOpsTopologyAdapter(
        base_url="https://weops.example.com",
        token=token,
        timeout=timeout,
        retry=retry,
        http_client=http_client or FakeHttpClient(responses),
        trace_id_factory=trace_id_factory or (lambda: "trace-1"),
    )


# --------------------------------------------------------------------------- #
# Header + URL building                                                         #
# --------------------------------------------------------------------------- #


def test_adapter_injects_x_token_and_trace_id():
    client = FakeHttpClient(responses=[FakeResponse(200, {"result": True, "data": [{"bk_obj_id": "bk_switch"}]})])
    adapter = _adapter(http_client=client)

    data = adapter.list_node_models()

    assert data == [{"bk_obj_id": "bk_switch"}]
    call = client.calls[0]
    assert call["headers"]["x-token"] == "service-token"
    assert call["headers"]["x-bklite-trace-id"] == "trace-1"
    assert call["url"] == "https://weops.example.com/open_api/bklite/network_topology/node_models/"


def test_adapter_uses_all_true_for_list_nodes_without_pagination_fallback():
    client = FakeHttpClient(responses=[FakeResponse(200, {"result": True, "data": {"count": 0, "results": []}})])
    adapter = _adapter(http_client=client)

    adapter.list_nodes({"bk_obj_id": "bk_switch", "keyword": "core", "page": 2, "page_size": 20})

    # The adapter passes ``params`` straight through to the HTTP client; we
    # inspect the dict directly instead of parsing a query string.
    sent_params = client.calls[0]["params"]
    assert sent_params == {"bk_obj_id": "bk_switch", "keyword": "core", "all": "true"}


def test_encode_node_ref_url_encodes_json_payload():
    ref = {"bk_obj_id": "bk_switch", "bk_inst_id": 10001, "network_collect_instance_id": 345, "plugin_template_id": 8}
    encoded = encode_node_ref(ref)
    assert "/" not in encoded
    assert "%" in encoded  # something has to be escaped (JSON braces, commas, etc.)
    # The decoded payload must reproduce the input dict exactly.
    assert json.loads(_url_unquote(encoded)) == ref


def _url_unquote(value: str) -> str:
    from urllib.parse import unquote

    return unquote(value)


def test_adapter_list_interfaces_encodes_node_ref_in_path():
    ref = {"bk_obj_id": "bk_switch", "bk_inst_id": 10001, "plugin_template_id": "cisco_c9300"}
    client = FakeHttpClient(responses=[FakeResponse(200, {"result": True, "data": {"items": [], "summary": {}, "status": "ok"}})])
    adapter = _adapter(http_client=client)
    adapter.list_interfaces(ref)

    url = client.calls[0]["url"]
    assert url.startswith("https://weops.example.com/open_api/bklite/network_topology/nodes/")
    assert url.endswith("/interfaces/")
    # Path component between ``nodes/`` and ``/interfaces/`` is URL-encoded JSON.
    path = urlparse(url).path
    encoded_segment = path.split("/nodes/", 1)[1].rsplit("/interfaces/", 1)[0]
    assert json.loads(_url_unquote(encoded_segment)) == ref


def test_adapter_list_metrics_uses_same_encoding():
    ref = {"bk_obj_id": "bk_firewall", "bk_inst_id": 20022, "plugin_template_id": "huawei_fw"}
    client = FakeHttpClient(responses=[FakeResponse(200, {"result": True, "data": {"items": [{"metric_field": "ifHCInOctets"}], "status": "ok"}})])
    adapter = _adapter(http_client=client)
    data = adapter.list_metrics(ref)
    assert data["items"][0]["metric_field"] == "ifHCInOctets"
    assert client.calls[0]["url"].endswith("/metrics/")


def test_adapter_dimension_values_posts_typed_payload():
    client = FakeHttpClient(
        responses=[FakeResponse(200, {"result": True, "data": {"items": [{"dimension": "ifDescr", "list": []}], "status": "ok"}})]
    )
    adapter = _adapter(http_client=client)
    adapter.list_dimension_values(
        {"bk_obj_id": "bk_switch", "bk_inst_id": 10001},
        {"metric_field": "ifHCInOctets", "result_table_id": "snmp_network"},
        ["ifDescr"],
    )
    sent = client.calls[0]["json"]
    assert sent["node_ref"]["bk_obj_id"] == "bk_switch"
    assert sent["metric_ref"]["metric_field"] == "ifHCInOctets"
    assert sent["dimension_keys"] == ["ifDescr"]


def test_adapter_batch_metric_values_passes_items():
    items = [{"request_id": "req-1"}]
    client = FakeHttpClient(responses=[FakeResponse(200, {"result": True, "data": {"items": items + [{"value": 1, "status": "ok"}]}})])
    adapter = _adapter(http_client=client)
    data = adapter.batch_metric_values(items)
    assert data["items"][0]["request_id"] == "req-1"
    assert client.calls[0]["json"] == {"items": items}


def test_adapter_batch_interface_status_includes_include_summary_flag():
    client = FakeHttpClient(responses=[FakeResponse(200, {"result": True, "data": {"items": [], "node_interface_summary": {}}})])
    adapter = _adapter(http_client=client)
    adapter.batch_interface_status([], include_summary=False)
    sent = client.calls[0]["json"]
    assert sent == {"items": [], "include_summary": False}


# --------------------------------------------------------------------------- #
# Response unwrapping                                                           #
# --------------------------------------------------------------------------- #


def test_adapter_unwraps_data_envelope():
    client = FakeHttpClient(responses=[FakeResponse(200, {"result": True, "data": {"items": [], "summary": {}, "status": "ok"}})])
    adapter = _adapter(http_client=client)
    data = adapter.list_interfaces({"bk_obj_id": "bk_switch", "bk_inst_id": 1})
    assert data == {"items": [], "summary": {}, "status": "ok"}


def test_adapter_unwraps_double_envelope_from_real_weops_renderer():
    """Real WeOps responses carry BOTH a renderer envelope (with code/message)
    AND a view-layer envelope nested inside ``data``. The adapter must peel
    both so callers see the actual service payload (issue 0046)."""
    real_payload = {"items": [], "summary": {"total": 0, "up": 0, "down": 0, "unknown": 0}, "status": "ok"}
    wrapped = {
        "result": True,
        "code": "20000",
        "message": "success",
        "data": {"result": True, "data": real_payload},
    }
    client = FakeHttpClient(responses=[FakeResponse(200, wrapped)])
    adapter = _adapter(http_client=client)
    data = adapter.list_interfaces({"bk_obj_id": "bk_switch", "bk_inst_id": 1})
    assert data == real_payload


def test_adapter_unwraps_double_envelope_for_list_node_models():
    """Same scenario, but for an endpoint whose inner payload is a list."""
    real_payload = [{"bk_obj_id": "bk_switch", "display_name": "交换机"}]
    wrapped = {
        "result": True,
        "code": "20000",
        "message": "success",
        "data": {"result": True, "data": real_payload},
    }
    client = FakeHttpClient(responses=[FakeResponse(200, wrapped)])
    adapter = _adapter(http_client=client)
    data = adapter.list_node_models()
    assert data == real_payload


def test_adapter_unwraps_double_envelope_for_batch_metric_values():
    """``batch_metric_values`` returns a dict with ``items`` and
    ``node_interface_summary``; verify double-envelope peeling for it."""
    real_payload = {"items": [{"value": 1, "status": "ok"}], "node_interface_summary": {}}
    wrapped = {
        "result": True,
        "code": "20000",
        "message": "success",
        "data": {"result": True, "data": real_payload},
    }
    client = FakeHttpClient(responses=[FakeResponse(200, wrapped)])
    adapter = _adapter(http_client=client)
    data = adapter.batch_metric_values([{"request_id": "r1"}])
    assert data == real_payload


def test_adapter_does_not_unwrap_nested_result_false():
    """A nested ``{"result": False, ...}`` (e.g. an item-level business
    error) must surface as a failure, NOT be silently peeled."""
    nested = {
        "result": True,
        "code": "20000",
        "message": "success",
        "data": {
            "result": False,
            "message": "scope 不足",
            "data": None,
        },
    }
    client = FakeHttpClient(responses=[FakeResponse(200, nested)])
    adapter = _adapter(http_client=client)
    with pytest.raises(WeOpsTopologyAdapterError) as exc:
        adapter.list_nodes({})
    assert exc.value.code == "weops_request_failed"
    assert "scope" in str(exc.value)


def test_adapter_returns_top_level_payload_when_no_envelope():
    """Some WeOps endpoints may not be wrapped; adapter should pass them through."""
    client = FakeHttpClient(responses=[FakeResponse(200, [{"bk_obj_id": "bk_switch"}])])
    adapter = _adapter(http_client=client)
    data = adapter.list_node_models()
    assert data == [{"bk_obj_id": "bk_switch"}]


def test_adapter_result_false_with_message_raises_weops_request_failed():
    client = FakeHttpClient(responses=[FakeResponse(200, {"result": False, "message": "scope 不足"})])
    adapter = _adapter(http_client=client)
    with pytest.raises(WeOpsTopologyAdapterError) as exc:
        adapter.list_nodes({})
    assert exc.value.code == "weops_request_failed"
    assert "scope" in str(exc.value)


# --------------------------------------------------------------------------- #
# Auth / token errors                                                           #
# --------------------------------------------------------------------------- #


def test_adapter_http_401_is_mapped_to_weops_token_invalid():
    client = FakeHttpClient(responses=[FakeResponse(401, {"message": "unauthorized"})])
    adapter = _adapter(http_client=client)
    with pytest.raises(WeOpsTopologyAdapterError) as exc:
        adapter.test_connection()
    assert exc.value.code == WEOPS_TOKEN_INVALID
    assert exc.value.status_code == 401


def test_adapter_http_403_is_mapped_to_weops_token_invalid():
    client = FakeHttpClient(responses=[FakeResponse(403, {"message": "missing x-token"})])
    adapter = _adapter(http_client=client)
    with pytest.raises(WeOpsTopologyAdapterError) as exc:
        adapter.list_nodes({})
    assert exc.value.code == WEOPS_TOKEN_INVALID
    assert exc.value.status_code == 403
    assert "Token" in str(exc.value)


# --------------------------------------------------------------------------- #
# Retry on transient transport errors                                           #
# --------------------------------------------------------------------------- #


def test_adapter_retries_transient_transport_error():
    class Boom(Exception):
        pass

    good = FakeResponse(200, {"result": True, "data": [{"bk_obj_id": "bk_switch"}]})
    client = FakeHttpClient(responses=[Boom("connection reset"), good])
    adapter = _adapter(http_client=client, retry=2)

    data = adapter.list_node_models()

    assert data == [{"bk_obj_id": "bk_switch"}]
    assert len(client.calls) == 2


def test_adapter_raises_after_max_retries():
    class Boom(Exception):
        pass

    client = FakeHttpClient(responses=[Boom("boom")] * 3)
    adapter = _adapter(http_client=client, retry=2)

    with pytest.raises(WeOpsTopologyAdapterError) as exc:
        adapter.list_node_models()
    assert exc.value.code == "weops_unavailable"
    assert len(client.calls) == 2


# --------------------------------------------------------------------------- #
# test_connection                                                               #
# --------------------------------------------------------------------------- #


def test_test_connection_passes_when_health_succeeds():
    client = FakeHttpClient(responses=[FakeResponse(200, {"result": True, "data": {"ok": True}})])
    adapter = _adapter(http_client=client)
    adapter.test_connection()  # does not raise
    assert client.calls[0]["url"] == "https://weops.example.com/open_api/bklite/network_topology/health/"


def test_test_connection_propagates_token_failure():
    client = FakeHttpClient(responses=[FakeResponse(403, {"message": "nope"})])
    adapter = _adapter(http_client=client)
    with pytest.raises(WeOpsTopologyAdapterError) as exc:
        adapter.test_connection()
    assert exc.value.code == WEOPS_TOKEN_INVALID


# --------------------------------------------------------------------------- #
# Item-level error_code mapping                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw_code, expected",
    [
        ("source_not_found", NetworkTopologyErrorType.SOURCE_NOT_FOUND),
        ("node_mismatch", NetworkTopologyErrorType.NODE_MISMATCH),
        ("source_inactive", NetworkTopologyErrorType.SOURCE_INACTIVE),
        ("template_mismatch", NetworkTopologyErrorType.TEMPLATE_MISMATCH),
        ("template_not_found", NetworkTopologyErrorType.TEMPLATE_NOT_FOUND),
        ("node_ref_invalid", NetworkTopologyErrorType.NODE_REF_INVALID),
        ("metric_not_found", NetworkTopologyErrorType.METRIC_NOT_FOUND),
        ("metric_query_failed", NetworkTopologyErrorType.METRIC_QUERY_FAILED),
        ("metric_no_data", NetworkTopologyErrorType.METRIC_NO_DATA),
        ("interface_relation_query_failed", NetworkTopologyErrorType.INTERFACE_RELATION_QUERY_FAILED),
        ("interface_query_failed", NetworkTopologyErrorType.INTERFACE_QUERY_FAILED),
        ("interface_not_found", NetworkTopologyErrorType.INTERFACE_NOT_FOUND),
        ("status_metric_not_found", NetworkTopologyErrorType.STATUS_METRIC_NOT_FOUND),
        ("status_query_failed", NetworkTopologyErrorType.STATUS_QUERY_FAILED),
        ("status_no_data", NetworkTopologyErrorType.STATUS_NO_DATA),
        ("future_error_we_dont_know_yet", NetworkTopologyErrorType.UNKNOWN),
        ("", NetworkTopologyErrorType.UNKNOWN),
        (None, NetworkTopologyErrorType.UNKNOWN),
    ],
)
def test_map_item_error_code_covers_all_known_codes_and_unknown_fallback(raw_code, expected):
    assert map_item_error_code(raw_code) == expected


def test_adapter_does_not_parse_item_error_codes_returned_in_data():
    """The adapter only cares about HTTP-level errors; item-level codes are
    surfaced to the runtime service layer untouched."""
    client = FakeHttpClient(
        responses=[
            FakeResponse(
                200,
                {
                    "result": True,
                    "data": {
                        "items": [
                            {
                                "request_id": "req-x",
                                "value": None,
                                "status": "error",
                                "error_code": "metric_no_data",
                            }
                        ]
                    },
                },
            )
        ]
    )
    adapter = _adapter(http_client=client)
    payload = adapter.batch_metric_values([])
    assert payload["items"][0]["error_code"] == "metric_no_data"


# --------------------------------------------------------------------------- #
# URL composition with URL-unsafe characters in the token                       #
# --------------------------------------------------------------------------- #


def test_adapter_does_not_choke_on_trailing_slash_in_base_url():
    client = FakeHttpClient(responses=[FakeResponse(200, {"result": True, "data": []})])
    adapter = _adapter(http_client=client)
    adapter.base_url = "https://weops.example.com/"  # set after construction
    data = adapter.list_node_models()
    assert data == []
    assert client.calls[0]["url"] == "https://weops.example.com/open_api/bklite/network_topology/node_models/"
