# -*- coding: utf-8 -*-
"""
End-to-end API tests for the network topology canvas.

Adapts to the project's ``CustomRenderer`` which wraps every response as
``{result, code=<status*100>, message, data}``. Our views surface custom
``WeOpsTopologyAdapterError.code`` strings via ``payload["data"]["code"]``,
while transport-level failures put status in ``payload["code"]`` and a
human-readable message in ``payload["message"]``.

Covers:

* Standard CRUD on the canvas (``POST /api/network_topology/``,
  ``GET /api/network_topology/``). Token is encrypted before persistence;
  plaintext is never echoed back.
* ``POST /api/network_topology/test_connection/`` against a mock adapter
  for the success and ``weops_token_invalid`` paths.
* ``GET /api/network_topology/<id>/runtime/`` against the in-memory
  ``NetworkTopologyRuntimeService`` flow: fresh payload, stale fallback
  when WeOps is down, and an error response when the cache is also gone.
* ``PUT /api/network_topology/<id>/config`` validates ``view_sets`` and
  cascade-removes links when a node is dropped.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.models.models import Directory, NetworkTopology
from apps.operation_analysis.services.network_topology import canvas_config
from apps.operation_analysis.services.network_topology.runtime import NetworkTopologyRuntimeService
from apps.operation_analysis.services.network_topology.weops_adapter import WEOPS_TOKEN_INVALID, WeOpsTopologyAdapterError
from apps.operation_analysis.views.network_topology_view import NetworkTopologyViewSet

# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #


def _request(method, path, user, data=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn(path, data=data, format="json") if data is not None else fn(path)
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _render(response):
    if not getattr(response, "rendered", False):
        response.render()
    return json.loads(response.rendered_content)


def _make_directory():
    return Directory.objects.create(name="网络拓扑目录", groups=[1])


def _make_topology(**overrides):
    directory = _make_directory()
    defaults = {
        "name": "核心网拓扑",
        "directory": directory,
        "groups": [1],
        "base_url": "https://weops.example.com",
        "token": "service-token",
    }
    defaults.update(overrides)
    return NetworkTopology.objects.create(**defaults)


# --------------------------------------------------------------------------- #
# Create                                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_create_canvas_requires_token(authenticated_user):
    authenticated_user.is_superuser = True
    directory = _make_directory()
    request = _request(
        "post",
        "/operation_analysis/api/network_topology/",
        authenticated_user,
        data={
            "name": "核心网拓扑",
            "directory": directory.id,
            "groups": [1],
            "base_url": "https://weops.example.com",
        },
    )

    response = NetworkTopologyViewSet.as_view({"post": "create"})(request)
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_create_canvas_encrypts_token_and_returns_token_set_flag(authenticated_user):
    authenticated_user.is_superuser = True
    directory = _make_directory()
    request = _request(
        "post",
        "/operation_analysis/api/network_topology/",
        authenticated_user,
        data={
            "name": "核心网拓扑",
            "directory": directory.id,
            "groups": [1],
            "base_url": "https://weops.example.com",
            "token": "plain-token",
        },
    )

    response = NetworkTopologyViewSet.as_view({"post": "create"})(request)
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    # 201 → renderer code is "20100".
    assert response.status_code == status.HTTP_201_CREATED
    assert payload["data"]["token_set"] is True
    assert "token" not in payload["data"]

    topology = NetworkTopology.objects.get(name="核心网拓扑")
    # DB column is encrypted.
    assert topology.token != "plain-token"
    assert topology.decrypt_token() == "plain-token"


@pytest.mark.django_db
def test_create_canvas_persists_groups_for_directory_tree_visibility(authenticated_user):
    """回归测试:`groups` 字段必须从 payload 落到 DB,否则新建画布会被
    :func:`DictDirectoryService.get_dict_trees` 的组织过滤剔除,目录树看不到。

    早期 :class:`NetworkTopologySerializer` 的 ``Meta.fields`` 没有列出
    ``groups``,DRF 会静默丢弃该字段,导致前端发来的 ``groups`` 落库为 ``[]``,
    进而目录树隐藏新画布(spec/requirements/运营分析/网络拓扑大屏需求设计 §2.1)。
    """
    authenticated_user.is_superuser = True
    directory = _make_directory()  # groups=[1]
    request = _request(
        "post",
        "/operation_analysis/api/network_topology/",
        authenticated_user,
        data={
            "name": "网络拓扑-groups-落库",
            "directory": directory.id,
            "groups": [1],
            "base_url": "https://weops.example.com",
            "token": "plain-token",
        },
    )

    response = NetworkTopologyViewSet.as_view({"post": "create"})(request)
    assert response.status_code == status.HTTP_201_CREATED

    topology = NetworkTopology.objects.get(name="网络拓扑-groups-落库")
    # 关键断言:groups 必须持久化,否则目录树会被 GroupPermissionMixin 过滤掉。
    assert topology.groups == [1], f"groups 字段必须从 payload 落到 DB,实际={topology.groups!r}"


@pytest.mark.django_db
def test_retrieve_canvas_does_not_expose_token(authenticated_user):
    """Single-object retrieval is the same code path the frontend uses after
    redirecting to ``/edit/<id>``. ``list`` goes through an organisation
    filter that depends on cookie state and is unreliable to drive on
    directly, so we exercise the security-sensitive serializer property
    via ``retrieve``.
    """
    authenticated_user.is_superuser = True
    topology = _make_topology(token="plain-token")

    request = _request(
        "get",
        f"/operation_analysis/api/network_topology/{topology.id}/",
        authenticated_user,
    )
    response = NetworkTopologyViewSet.as_view({"get": "retrieve"})(request, pk=str(topology.id))
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["token_set"] is True
    assert "token" not in payload["data"]
    raw = json.dumps(payload)
    assert "plain-token" not in raw


@pytest.mark.django_db
def test_create_canvas_rejects_placeholder_token(authenticated_user):
    authenticated_user.is_superuser = True
    directory = _make_directory()
    request = _request(
        "post",
        "/operation_analysis/api/network_topology/",
        authenticated_user,
        data={
            "name": "占位符画布",
            "directory": directory.id,
            "groups": [1],
            "base_url": "https://weops.example.com",
            "token": "******",
        },
    )

    response = NetworkTopologyViewSet.as_view({"post": "create"})(request)
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "token" in payload["message"] or "token" in json.dumps(payload)


# --------------------------------------------------------------------------- #
# test_connection                                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_test_connection_succeeds_against_mock_adapter(monkeypatch, authenticated_user):
    authenticated_user.is_superuser = True

    captured = {}

    class FakeAdapter:
        def __init__(self, base_url, token, **kwargs):
            captured["base_url"] = base_url
            captured["token"] = token

        def test_connection(self):
            return None

    def fake_constructor(**kwargs):
        captured["ctor_kwargs"] = kwargs
        return FakeAdapter(**kwargs)

    monkeypatch.setattr(
        "apps.operation_analysis.views.network_topology_view.WeOpsTopologyAdapter",
        fake_constructor,
    )

    request = _request(
        "post",
        "/operation_analysis/api/network_topology/test_connection/",
        authenticated_user,
        data={
            "base_url": "https://weops.example.com",
            "token": "validation-token",
        },
    )

    response = NetworkTopologyViewSet.as_view({"post": "test_connection"})(request)
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused

    assert response.status_code == status.HTTP_200_OK
    assert payload["data"] == {"status": "ok"}
    # Nothing persisted by the test_connection endpoint — this is a
    # verification call only.
    assert captured["token"] == "validation-token"


@pytest.mark.django_db
def test_saved_test_connection_reuses_existing_token(monkeypatch, authenticated_user):
    authenticated_user.is_superuser = True
    topology = _make_topology(token="saved-token")
    captured = {}

    class FakeAdapter:
        def __init__(self, base_url, token, **kwargs):
            captured["base_url"] = base_url
            captured["token"] = token

        def test_connection(self):
            return None

    monkeypatch.setattr(
        "apps.operation_analysis.views.network_topology_view.WeOpsTopologyAdapter",
        lambda **kwargs: FakeAdapter(**kwargs),
    )

    request = _request(
        "post",
        f"/operation_analysis/api/network_topology/{topology.id}/test_connection/",
        authenticated_user,
        data={"base_url": "https://new-weops.example.com"},
    )

    response = NetworkTopologyViewSet.as_view({"post": "test_saved_connection"})(request, pk=str(topology.id))
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused

    assert response.status_code == status.HTTP_200_OK
    assert payload["data"] == {"status": "ok"}
    assert captured == {
        "base_url": "https://new-weops.example.com",
        "token": "saved-token",
    }


@pytest.mark.django_db
def test_test_connection_surfaces_weops_token_invalid_in_data(monkeypatch, authenticated_user):
    authenticated_user.is_superuser = True

    class FakeAdapter:
        def test_connection(self):
            raise WeOpsTopologyAdapterError(
                "WeOps Token 已失效",
                code=WEOPS_TOKEN_INVALID,
                status_code=403,
            )

    monkeypatch.setattr(
        "apps.operation_analysis.views.network_topology_view.WeOpsTopologyAdapter",
        lambda **kwargs: FakeAdapter(),
    )

    request = _request(
        "post",
        "/operation_analysis/api/network_topology/test_connection/",
        authenticated_user,
        data={
            "base_url": "https://weops.example.com",
            "token": "stale-token",
        },
    )

    response = NetworkTopologyViewSet.as_view({"post": "test_connection"})(request)
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    assert response.status_code == status.HTTP_403_FORBIDDEN
    # Renderer uses ``<status>*100`` for the public ``code`` field, but the
    # canonical ``WeOpsTopologyAdapterError.code`` is preserved under
    # ``payload["data"]["code"]`` for downstream consumers.
    assert payload["code"] == "40300"
    assert payload["data"]["code"] == WEOPS_TOKEN_INVALID


@pytest.mark.django_db
def test_test_connection_rejects_bad_url(authenticated_user):
    authenticated_user.is_superuser = True
    request = _request(
        "post",
        "/operation_analysis/api/network_topology/test_connection/",
        authenticated_user,
        data={
            "base_url": "weops.example.com",  # missing scheme
            "token": "x",
        },
    )
    response = NetworkTopologyViewSet.as_view({"post": "test_connection"})(request)
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# --------------------------------------------------------------------------- #
# Runtime + cache                                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_runtime_returns_error_without_cache_fallback_when_weops_unavailable(monkeypatch, authenticated_user):
    """需求变更:每次进入画布都重新请求 WeOps,失败直接返回错误,不再回退
    到 ``last_runtime_cache``(spec/requirements/运营分析/网络拓扑大屏
    需求设计 §7.6)。原先的 stale fallback 行为在 P1 后由缓存层单独管理。
    """
    authenticated_user.is_superuser = True
    topology = _make_topology()
    topology.view_sets = {
        "nodes": [
            _node_payload("node-1", "bk_switch", 10001)
            | {
                "metrics": [
                    {
                        "metric_field": "ifHCInOctets",
                        "result_table_id": "snmp_network",
                        "display_name": "入口流量",
                        "unit": "bps",
                        "dimensions": {},
                        "thresholds": [{"value": 0, "color": "#22c55e"}],
                    }
                ]
            }
        ],
        "links": [
            _link_payload("link-1", "node-1", "node-1"),
        ],
    }
    # 即便历史有 cache,也不允许 stale fallback —— 直接 502。
    topology.last_runtime_cache = NetworkTopologyRuntimeService.cache_payload({"nodes": [{"id": "node-1", "outer_color": "#dc2626"}], "links": []})
    topology.save()

    monkeypatch.setattr(
        "apps.operation_analysis.views.network_topology_view._adapter_for",
        lambda topology_obj: _exploding_adapter(),
    )

    request = _request(
        "get",
        f"/operation_analysis/api/network_topology/{topology.id}/runtime/",
        authenticated_user,
    )
    response = NetworkTopologyViewSet.as_view({"get": "runtime"})(request, pk=str(topology.id))
    payload = _render(response)

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert payload["data"]["stale"] is False
    assert payload["data"]["code"] == "weops_unavailable"


@pytest.mark.django_db
def test_runtime_returns_error_when_cache_expired(monkeypatch, authenticated_user):
    authenticated_user.is_superuser = True
    topology = _make_topology()
    topology.view_sets = {
        "nodes": [
            _node_payload("node-1", "bk_switch", 10001)
            | {
                "metrics": [
                    {
                        "metric_field": "ifHCInOctets",
                        "result_table_id": "snmp_network",
                        "display_name": "入口流量",
                        "unit": "bps",
                        "dimensions": {},
                        "thresholds": [{"value": 0, "color": "#22c55e"}],
                    }
                ]
            }
        ],
        "links": [
            _link_payload("link-1", "node-1", "node-1"),
        ],
    }
    topology.last_runtime_cache = {
        "nodes": [{"id": "node-1"}],
        NetworkTopologyRuntimeService.CACHE_GENERATED_AT_KEY: (
            timezone.now() - timedelta(seconds=NetworkTopologyRuntimeService.CACHE_TTL_SECONDS + 30)
        ).isoformat(),
    }
    topology.save()

    monkeypatch.setattr(
        "apps.operation_analysis.views.network_topology_view._adapter_for",
        lambda topology_obj: _exploding_adapter(),
    )

    request = _request(
        "get",
        f"/operation_analysis/api/network_topology/{topology.id}/runtime/",
        authenticated_user,
    )
    response = NetworkTopologyViewSet.as_view({"get": "runtime"})(request, pk=str(topology.id))
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert payload["result"] is False
    assert payload["data"]["stale"] is False
    assert "nodes" not in payload["data"]


@pytest.mark.django_db
def test_runtime_token_invalid_returns_error_without_cache_fallback(monkeypatch, authenticated_user):
    """需求变更:WeOps Token 失效时不再 stale fallback 到 last_runtime_cache,
    直接返回 401 + 错误信息(spec/requirements/运营分析/网络拓扑大屏
    需求设计 §7.6)。前端在 ``fatalMessage`` 上显示横幅,让用户去画布
    配置页改 token。
    """
    authenticated_user.is_superuser = True
    topology = _make_topology()
    topology.view_sets = {
        "nodes": [
            _node_payload("node-1", "bk_switch", 10001)
            | {
                "metrics": [
                    {
                        "metric_field": "ifHCInOctets",
                        "result_table_id": "snmp_network",
                        "display_name": "入口流量",
                        "unit": "bps",
                        "dimensions": {},
                        "thresholds": [{"value": 0, "color": "#22c55e"}],
                    }
                ]
            }
        ],
        "links": [
            _link_payload("link-1", "node-1", "node-1"),
        ],
    }
    # 即便历史有 cache,也不允许 stale fallback。
    topology.last_runtime_cache = NetworkTopologyRuntimeService.cache_payload({"nodes": [{"id": "node-1"}], "links": []})
    topology.save()

    class TokenInvalidAdapter:
        def batch_metric_values(self, items):
            raise WeOpsTopologyAdapterError(
                "WeOps Token 已失效",
                code=WEOPS_TOKEN_INVALID,
                status_code=403,
            )

        def batch_interface_status(self, items, include_summary=True):
            raise WeOpsTopologyAdapterError(
                "WeOps Token 已失效",
                code=WEOPS_TOKEN_INVALID,
                status_code=403,
            )

    monkeypatch.setattr(
        "apps.operation_analysis.views.network_topology_view._adapter_for",
        lambda topology_obj: TokenInvalidAdapter(),
    )

    request = _request(
        "get",
        f"/operation_analysis/api/network_topology/{topology.id}/runtime/",
        authenticated_user,
    )
    response = NetworkTopologyViewSet.as_view({"get": "runtime"})(request, pk=str(topology.id))
    payload = _render(response)
    # 直接返回 403 + weops_token_invalid,不再 stale fallback。
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert payload["data"]["code"] == WEOPS_TOKEN_INVALID
    assert "stale" not in payload["data"] or payload["data"].get("stale") is False


def _exploding_adapter():
    class _Adapter:
        def batch_metric_values(self, items):
            raise WeOpsTopologyAdapterError("WeOps 不可用", code="weops_unavailable", status_code=502)

        def batch_interface_status(self, items, include_summary=True):
            raise WeOpsTopologyAdapterError("WeOps 不可用", code="weops_unavailable", status_code=502)

    return _Adapter()


# --------------------------------------------------------------------------- #
# view_sets config + cascade                                                    #
# --------------------------------------------------------------------------- #


def _node_payload(node_id, bk_obj_id="bk_switch", bk_inst_id=10001):
    return {
        "id": node_id,
        "bk_obj_id": bk_obj_id,
        "bk_inst_id": bk_inst_id,
        "bk_inst_name": f"{bk_obj_id}-{bk_inst_id}",
        "ip_addr": "10.0.0.1",
        "network_collect_task_id": 12,
        "network_collect_instance_id": 345,
        "plugin_group_id": 3,
        "plugin_template_id": "x",
        "position": {"x": 200, "y": 120},
        "style": {},
        "metrics": [],
    }


def _link_payload(link_id, source, target):
    return {
        "id": link_id,
        "source_node_id": source,
        "target_node_id": target,
        "is_draft": False,
        "port_pairs": [
            {
                "source_interface": {"bk_obj_id": "bk_interface", "bk_inst_id": 90001, "interface_name": "GigE0/1"},
                "target_interface": {"bk_obj_id": "bk_interface", "bk_inst_id": 90002, "interface_name": "GigE0/1"},
            }
        ],
        "style": {},
    }


@pytest.mark.django_db
def test_put_config_validates_and_persists_view_sets(authenticated_user):
    authenticated_user.is_superuser = True
    topology = _make_topology()

    payload = {
        "nodes": [
            _node_payload("node-1"),
            _node_payload("node-2", "bk_router", 10002),
        ],
        "links": [_link_payload("link-1", "node-1", "node-2")],
    }

    request = _request(
        "put",
        f"/operation_analysis/api/network_topology/{topology.id}/config/",
        authenticated_user,
        data=payload,
    )

    response = NetworkTopologyViewSet.as_view({"put": "config"})(request, pk=str(topology.id))
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    body = _render(response)

    assert response.status_code == status.HTTP_200_OK
    topology.refresh_from_db()
    assert {n["id"] for n in canvas_config.dump(topology)["nodes"]} == {"node-1", "node-2"}
    assert body["data"]["links"][0]["port_pairs"][0]["source_interface"]["bk_inst_id"] == 90001


@pytest.mark.django_db
def test_get_config_returns_persisted_view_sets(authenticated_user):
    authenticated_user.is_superuser = True
    topology = _make_topology()
    topology.view_sets = {
        "nodes": [_node_payload("node-1"), _node_payload("node-2", "bk_router", 10002)],
        "links": [],
    }
    topology.save()

    request = _request(
        "get",
        f"/operation_analysis/api/network_topology/{topology.id}/config/",
        authenticated_user,
    )
    response = NetworkTopologyViewSet.as_view({"get": "config"})(request, pk=str(topology.id))
    payload = _render(response)

    assert response.status_code == 200
    assert {n["id"] for n in payload["data"]["nodes"]} == {"node-1", "node-2"}
    assert payload["data"]["links"] == []


@pytest.mark.django_db
def test_put_config_rejects_invalid_view_sets(authenticated_user):
    authenticated_user.is_superuser = True
    topology = _make_topology()

    request = _request(
        "put",
        f"/operation_analysis/api/network_topology/{topology.id}/config/",
        authenticated_user,
        data={
            "nodes": [_node_payload("node-1")],
            "links": [
                {"id": "link-1", "source_node_id": "node-1", "target_node_id": "ghost", "port_pairs": []},
            ],
        },
    )

    response = NetworkTopologyViewSet.as_view({"put": "config"})(request, pk=str(topology.id))
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    # Renderer ``message`` field carries both errors (the bad node id and
    # the missing port pair). Inspect the rendered top-level fields
    # rather than re-serializing to avoid double-encoded UTF-8 escapes.
    joined = f"{payload['message']} {json.dumps(payload)}"
    assert "ghost" in joined
    assert "端口" in joined


@pytest.mark.django_db
def test_delete_node_endpoint_cascades_to_links(authenticated_user):
    authenticated_user.is_superuser = True
    topology = _make_topology()
    topology.view_sets = {
        "nodes": [_node_payload("node-1"), _node_payload("node-2", "bk_router", 10002)],
        "links": [_link_payload("link-1", "node-1", "node-2")],
    }
    topology.save()

    request = _request(
        "delete",
        f"/operation_analysis/api/network_topology/{topology.id}/config/nodes/node-1/",
        authenticated_user,
    )

    response = NetworkTopologyViewSet.as_view({"delete": "remove_node"})(request, pk=str(topology.id), node_id="node-1")
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    assert response.status_code == status.HTTP_200_OK
    topology.refresh_from_db()
    node_ids = [n["id"] for n in canvas_config.dump(topology)["nodes"]]
    link_ids = [link["id"] for link in canvas_config.dump(topology)["links"]]
    assert node_ids == ["node-2"]
    assert link_ids == []


# --------------------------------------------------------------------------- #
# WeOps proxy endpoints                                                          #
# --------------------------------------------------------------------------- #


def _patch_weops_adapter(monkeypatch, topology, *, call_log, return_value=None, raise_exc=None):
    """Swap the canvas' adapter so proxy actions hit an in-memory fake."""
    from apps.operation_analysis.views import network_topology_view as v

    class _FakeAdapter:
        def list_node_models(self_inner):
            call_log.append("list_node_models")
            if raise_exc is not None:
                raise raise_exc
            return return_value if return_value is not None else [{"bk_obj_id": "bk_switch"}]

        def list_nodes(self_inner, filters):
            call_log.append(("list_nodes", filters))
            if raise_exc is not None:
                raise raise_exc
            return return_value if return_value is not None else {"count": 0, "results": []}

        def list_interfaces(self_inner, ref):
            call_log.append(("list_interfaces", ref))
            if raise_exc is not None:
                raise raise_exc
            return return_value if return_value is not None else {"items": [], "summary": {}}

        def list_metrics(self_inner, ref):
            call_log.append(("list_metrics", ref))
            if raise_exc is not None:
                raise raise_exc
            return return_value if return_value is not None else {"items": [], "status": "ok"}

        def list_dimension_values(self_inner, node_ref, metric_ref, dimension_keys):
            call_log.append(("list_dimension_values", node_ref, metric_ref, dimension_keys))
            if raise_exc is not None:
                raise raise_exc
            return return_value if return_value is not None else {"items": [], "status": "ok"}

    monkeypatch.setattr(v, "_adapter_for", lambda canvas: _FakeAdapter())


@pytest.mark.django_db
def test_weops_proxy_node_models(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    topology = _make_topology()
    log = []
    _patch_weops_adapter(monkeypatch, topology, call_log=log, return_value=[{"bk_obj_id": "bk_switch"}])

    request = _request("get", f"/operation_analysis/api/network_topology/{topology.id}/weops/node_models/", authenticated_user)
    response = NetworkTopologyViewSet.as_view({"get": "weops_node_models"})(request, pk=str(topology.id))
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    body = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert log == ["list_node_models"]
    assert body["data"] == [{"bk_obj_id": "bk_switch"}]


@pytest.mark.django_db
def test_weops_proxy_nodes_passes_filters(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    topology = _make_topology()
    log = []
    _patch_weops_adapter(monkeypatch, topology, call_log=log)

    request = _request(
        "get",
        f"/operation_analysis/api/network_topology/{topology.id}/weops/nodes/?bk_obj_id=bk_switch&keyword=core&page=2",
        authenticated_user,
    )
    response = NetworkTopologyViewSet.as_view({"get": "weops_nodes"})(request, pk=str(topology.id))
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    assert response.status_code == status.HTTP_200_OK
    assert log[0][0] == "list_nodes"
    filters = log[0][1]
    assert filters["bk_obj_id"] == "bk_switch"
    assert filters["keyword"] == "core"
    assert filters["all"] == "true"
    assert "page" not in filters
    assert "page_size" not in filters


@pytest.mark.django_db
def test_weops_proxy_node_interfaces_decodes_node_ref(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    topology = _make_topology()
    log = []
    _patch_weops_adapter(monkeypatch, topology, call_log=log)

    from urllib.parse import quote

    node_ref = {
        "bk_obj_id": "bk_switch",
        "bk_inst_id": 383680,
        "network_collect_task_id": 170,
        "network_collect_instance_id": 1935,
        "plugin_template_id": 1934,
    }
    encoded = quote(json.dumps(node_ref, separators=(",", ":")), safe="")
    request = _request(
        "get",
        f"/operation_analysis/api/network_topology/{topology.id}/weops/nodes/{encoded}/interfaces/",
        authenticated_user,
    )
    response = NetworkTopologyViewSet.as_view({"get": "weops_node_interfaces"})(request, pk=str(topology.id), node_ref=encoded)
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    assert response.status_code == status.HTTP_200_OK
    # The adapter must have received the *decoded* dict, not the URL string.
    received_ref = log[0][1]
    assert received_ref == node_ref


@pytest.mark.django_db
def test_weops_proxy_node_interfaces_bad_node_ref_returns_400(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    topology = _make_topology()
    log = []
    _patch_weops_adapter(monkeypatch, topology, call_log=log)

    request = _request(
        "get",
        f"/operation_analysis/api/network_topology/{topology.id}/weops/nodes/not-json/interfaces/",
        authenticated_user,
    )
    response = NetworkTopologyViewSet.as_view({"get": "weops_node_interfaces"})(request, pk=str(topology.id), node_ref="not-json")
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert log == []  # adapter was not even called


@pytest.mark.django_db
def test_weops_proxy_dimension_values_forwards_payload(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    topology = _make_topology()
    log = []
    _patch_weops_adapter(monkeypatch, topology, call_log=log)

    request = _request(
        "post",
        f"/operation_analysis/api/network_topology/{topology.id}/weops/dimension_values/",
        authenticated_user,
        data={
            "node_ref": {"bk_obj_id": "bk_switch", "bk_inst_id": 1},
            "metric_ref": {"metric_field": "ifHCInOctets", "result_table_id": "rt"},
            "dimension_keys": ["ifDescr"],
        },
    )
    response = NetworkTopologyViewSet.as_view({"post": "weops_dimension_values"})(request, pk=str(topology.id))
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    assert response.status_code == status.HTTP_200_OK
    assert log[0][0] == "list_dimension_values"
    node_ref, metric_ref, keys = log[0][1], log[0][2], log[0][3]
    assert node_ref == {"bk_obj_id": "bk_switch", "bk_inst_id": 1}
    assert metric_ref == {"metric_field": "ifHCInOctets", "result_table_id": "rt"}
    assert keys == ["ifDescr"]


@pytest.mark.django_db
def test_weops_proxy_translates_token_invalid_to_403(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    topology = _make_topology()
    log = []
    _patch_weops_adapter(
        monkeypatch,
        topology,
        call_log=log,
        raise_exc=WeOpsTopologyAdapterError(
            "WeOps Token 已失效，请更新画布配置",
            code=WEOPS_TOKEN_INVALID,
            status_code=403,
        ),
    )
    request = _request("get", f"/operation_analysis/api/network_topology/{topology.id}/weops/node_models/", authenticated_user)
    response = NetworkTopologyViewSet.as_view({"get": "weops_node_models"})(request, pk=str(topology.id))
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    body = _render(response)
    assert response.status_code == 403
    assert body["data"]["code"] == "weops_token_invalid"


@pytest.mark.django_db
def test_weops_proxy_translates_unavailable_to_502(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    topology = _make_topology()
    log = []
    _patch_weops_adapter(
        monkeypatch,
        topology,
        call_log=log,
        raise_exc=WeOpsTopologyAdapterError("network down", code="weops_unavailable", status_code=502),
    )
    request = _request("get", f"/operation_analysis/api/network_topology/{topology.id}/weops/node_models/", authenticated_user)
    response = NetworkTopologyViewSet.as_view({"get": "weops_node_models"})(request, pk=str(topology.id))
    payload = _render(response)  # noqa: F841 — exercises the response renderer even when unused
    body = _render(response)
    assert response.status_code == 502
    assert body["data"]["code"] == "weops_unavailable"
