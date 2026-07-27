# -*- coding: utf-8 -*-
"""
View layer for the network-topology canvas.

Public endpoints (mounted under ``/api/network_topology/``):

* ``GET  /`` — list (token never returned)
* ``POST /`` — create canvas (validates base_url + token)
* ``GET  /<id>/`` — retrieve (token never returned)
* ``PUT  /<id>/`` — update metadata (token optional)
* ``DELETE /<id>/`` — remove canvas
* ``POST /test_connection/`` — probe the WeOps API and surface
  ``weops_token_invalid`` (401/403) distinctly from transport errors.
* ``PUT  /<id>/config/`` — replace ``view_sets`` JSON.
* ``DELETE /<id>/config/nodes/<node_id>/`` — cascade remove a node.
* ``GET  /<id>/weops/node_models/`` — proxy: list WeOps device models.
* ``GET  /<id>/weops/nodes/`` — proxy: list WeOps device instances.
* ``GET  /<id>/weops/nodes/<node_ref>/interfaces/`` — proxy: list
  interfaces for a node.
* ``GET  /<id>/weops/nodes/<node_ref>/metrics/`` — proxy: list
  metrics for a node.
* ``POST /<id>/weops/dimension_values/`` — proxy: list dimension
  values for a (node, metric) pair.

The WeOps proxy endpoints exist so the React frontend can stay on the
bk-lite origin (avoids CORS preflights and keeps ``x-token`` server-side
where it belongs). They never persist data — they simply relay the
request to the upstream WeOps service configured on the canvas.
"""

from __future__ import annotations

import json
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.operation_analysis.models.models import NetworkTopology
from apps.operation_analysis.serializers.network_topology_serializers import (
    NetworkTopologySerializer,
    NetworkTopologyWeOpsTestConnectionSerializer,
    decrypt_token,
)
from apps.operation_analysis.services.network_topology import canvas_config
from apps.operation_analysis.services.network_topology.runtime import NetworkTopologyRuntimeService
from apps.operation_analysis.services.network_topology.weops_adapter import WeOpsTopologyAdapter, WeOpsTopologyAdapterError

logger = logging.getLogger("apps.operation_analysis.network_topology")


# --------------------------------------------------------------------------- #
# Adapter factory                                                               #
# --------------------------------------------------------------------------- #


def _adapter_for(topology: NetworkTopology) -> WeOpsTopologyAdapter:
    """Build a :class:`WeOpsTopologyAdapter` for the given topology."""
    return WeOpsTopologyAdapter(
        base_url=topology.base_url,
        token=decrypt_token(topology.token),
    )


# --------------------------------------------------------------------------- #
# ViewSet                                                                       #
# --------------------------------------------------------------------------- #


class NetworkTopologyViewSet(ModelViewSet):
    """DRF view for the canvas CRUD + WeOps-aware actions."""

    queryset = NetworkTopology.objects.all()
    serializer_class = NetworkTopologySerializer

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _adapter_error_response(exc: WeOpsTopologyAdapterError) -> Response:
        """Translate a :class:`WeOpsTopologyAdapterError` into a response.

        The frontend distinguishes ``weops_token_invalid`` (re-prompt
        the user for a new token) from transport errors. We surface the
        canonical ``code`` in ``data.data.code`` and let the renderer
        decide the HTTP status via the ``status_code`` attribute.

        响应体采用 :class:`rest_framework.exceptions.ValidationError` 的
        ``{"detail": ..., "data": ...}`` 形式 —— :class:`CustomRenderer`
        会用 ``detail`` 直接填到顶层的 ``message`` 字段,避免把整个
        ``data`` dict 序列化成 ``"data:{...}"`` 这种 Python repr 字符串
        显示到 antd ``message.error`` 上
        (specs/capabilities/legacy-requirements-运营分析-20260707-运营分析-网络拓扑大屏需求设计.md §6.1)。
        """
        message = str(exc) or exc.code
        body = {
            "detail": message,
            "data": {
                "code": exc.code,
                "message": message,
                "stale": False,
            },
        }
        return Response(body, status=exc.status_code or status.HTTP_502_BAD_GATEWAY)

    @staticmethod
    def _coerce_validation_error(exc: DjangoValidationError) -> DRFValidationError:
        """Map a :class:`django.core.exceptions.ValidationError` onto DRF.

        DRF's exception handler only converts its own ``ValidationError``
        subclass into a 400; the Django one needs an explicit translation
        to keep the response body consistent with other endpoints.
        """
        if hasattr(exc, "message_dict"):
            detail = exc.message_dict
        elif hasattr(exc, "messages"):
            detail = {"non_field_errors": list(exc.messages)}
        else:
            detail = {"non_field_errors": [str(exc)]}
        return DRFValidationError(detail)

    # ------------------------------------------------------------------ #
    # Custom actions                                                       #
    # ------------------------------------------------------------------ #

    @action(detail=False, methods=["post"], url_path="test_connection")
    def test_connection(self, request):
        """Probe the WeOps API. Never persists the credentials."""
        serializer = NetworkTopologyWeOpsTestConnectionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        adapter = WeOpsTopologyAdapter(
            base_url=payload["base_url"],
            token=payload["token"],
        )
        try:
            adapter.test_connection()
        except WeOpsTopologyAdapterError as exc:
            return self._adapter_error_response(exc)
        return Response({"status": "ok"})

    @action(detail=True, methods=["post"], url_path="test_connection")
    def test_saved_connection(self, request, pk: str | None = None):
        """Probe an existing topology connection.

        Editing forms may leave ``token`` blank/placeholder to keep the
        saved token. In that case, use the encrypted token already stored on
        the canvas row; if the user enters a replacement token, test that one.
        """
        topology = self.get_object()
        payload = request.data or {}
        base_url = payload.get("base_url") or topology.base_url
        token = payload.get("token")
        if not token or token == "******":
            token = decrypt_token(topology.token)
        serializer = NetworkTopologyWeOpsTestConnectionSerializer(data={"base_url": base_url, "token": token})
        serializer.is_valid(raise_exception=True)
        adapter = WeOpsTopologyAdapter(
            base_url=serializer.validated_data["base_url"],
            token=serializer.validated_data["token"],
        )
        try:
            adapter.test_connection()
        except WeOpsTopologyAdapterError as exc:
            return self._adapter_error_response(exc)
        return Response({"status": "ok"})

    @action(detail=True, methods=["get", "put"], url_path="config")
    def config(self, request, pk: str | None = None):
        """Read or replace the canvas ``view_sets`` JSON.

        * ``GET``  — return the current ``view_sets`` (defensive copy).
        * ``PUT``  — replace ``view_sets`` atomically after running the
          full structural validator; same rules as the serializer's
          ``validate_view_sets``.

        design.md §8 says the proxy should expose both verbs; the
        frontend currently uses ``getViewSets`` on mount, so the GET
        branch is what unblocks the entry-time load.
        """
        topology = self.get_object()
        if request.method == "GET":
            return Response(canvas_config.dump(topology))
        try:
            updated = canvas_config.replace(topology, request.data or {})
        except DjangoValidationError as exc:
            raise self._coerce_validation_error(exc)
        return Response(updated)

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"config/nodes/(?P<node_id>[^/.]+)",
    )
    def remove_node(self, request, pk: str | None = None, node_id: str | None = None):
        """Application-level cascade delete for a node (and any link that
        references it)."""
        topology = self.get_object()
        if not node_id:
            raise DRFValidationError({"node_id": ["缺少 node_id 路径参数"]})
        updated = canvas_config.cascade_remove_node(topology, node_id)
        return Response(updated)

    # ------------------------------------------------------------------ #
    # WeOps proxy endpoints                                                #
    # ------------------------------------------------------------------ #
    #
    # The frontend never talks to WeOps directly: it calls these proxy
    # endpoints, which keep ``x-token`` server-side and avoid CORS. We
    # centralise the error → response translation through
    # ``_run_weops_call`` so each action stays a one-liner.
    def _run_weops_call(self, canvas_id, fn, *args, **kwargs):
        """Run ``fn`` against the canvas' WeOps adapter and translate errors."""
        topology = self.get_object() if canvas_id is not None else None
        if topology is None:
            raise DRFValidationError({"id": ["缺少画布 id"]})
        adapter = _adapter_for(topology)
        try:
            return Response(fn(adapter, *args, **kwargs))
        except WeOpsTopologyAdapterError as exc:
            return self._adapter_error_response(exc)

    @action(detail=True, methods=["get"], url_path=r"weops/node_models")
    def weops_node_models(self, request, pk: str | None = None):
        """Proxy: list the 4 hard-coded WeOps device model types."""
        return self._run_weops_call(pk, lambda adapter: adapter.list_node_models())

    @action(detail=True, methods=["get"], url_path=r"weops/nodes")
    def weops_nodes(self, request, pk: str | None = None):
        """Proxy: list WeOps device instances.

        Forwards ``bk_obj_id`` and ``keyword`` query params. The adapter sends
        only ``all=true`` for the WeOps full-library branch.
        """
        filters = {
            "bk_obj_id": request.GET.get("bk_obj_id", ""),
            "keyword": request.GET.get("keyword", ""),
            "all": request.GET.get("all", "true"),
        }
        return self._run_weops_call(pk, lambda adapter: adapter.list_nodes(filters))

    @action(
        detail=True,
        methods=["get"],
        url_path=r"weops/nodes/(?P<node_ref>[^/]+)/interfaces",
    )
    def weops_node_interfaces(self, request, pk: str | None = None, node_ref: str | None = None):
        """Proxy: list the interfaces of a WeOps node.

        ``node_ref`` comes URL-encoded from the frontend (a JSON dict of
        ``bk_obj_id`` / ``bk_inst_id`` / ``network_collect_*`` /
        ``plugin_*`` fields). We decode it back into a dict before
        handing it to the adapter, which re-encodes it for the upstream
        path segment.
        """
        ref = self._decode_node_ref(node_ref)
        if not isinstance(ref, dict):
            raise DRFValidationError({"node_ref": ["node_ref 解析失败"]})
        return self._run_weops_call(pk, lambda adapter: adapter.list_interfaces(ref))

    @action(
        detail=True,
        methods=["get"],
        url_path=r"weops/nodes/(?P<node_ref>[^/]+)/metrics",
    )
    def weops_node_metrics(self, request, pk: str | None = None, node_ref: str | None = None):
        """Proxy: list the metrics a WeOps node exposes."""
        ref = self._decode_node_ref(node_ref)
        if not isinstance(ref, dict):
            raise DRFValidationError({"node_ref": ["node_ref 解析失败"]})
        return self._run_weops_call(pk, lambda adapter: adapter.list_metrics(ref))

    @action(detail=True, methods=["post"], url_path=r"weops/dimension_values")
    def weops_dimension_values(self, request, pk: str | None = None):
        """Proxy: list dimension values for a (node, metric) pair.

        Body shape::

            {
                "node_ref": {...},
                "metric_ref": {"metric_field": "...", "result_table_id": "..."},
                "dimension_keys": ["ifDescr", ...]
            }
        """
        payload = request.data or {}
        node_ref = payload.get("node_ref") or {}
        metric_ref = payload.get("metric_ref") or {}
        dimension_keys = payload.get("dimension_keys") or []
        if not isinstance(node_ref, dict) or not node_ref:
            raise DRFValidationError({"node_ref": ["node_ref 必填"]})
        if not isinstance(metric_ref, dict) or not metric_ref:
            raise DRFValidationError({"metric_ref": ["metric_ref 必填"]})
        return self._run_weops_call(
            pk,
            lambda adapter: adapter.list_dimension_values(node_ref, metric_ref, dimension_keys),
        )

    @action(detail=True, methods=["post"], url_path=r"weops/metric_values")
    def weops_metric_values(self, request, pk: str | None = None):
        """Proxy: query current metric values for draft node metric config.

        整图 runtime 接口已废弃。编辑器按节点批量查询当前值,
        使新选指标在保存整个画布前即可展示。
        """
        payload = request.data or {}
        items = payload.get("items") or []
        if not isinstance(items, list):
            raise DRFValidationError({"items": ["items 必须是数组"]})
        return self._run_weops_call(pk, lambda adapter: adapter.batch_metric_values(items))

    @action(detail=True, methods=["post"], url_path=r"weops/link_runtime")
    def weops_link_runtime(self, request, pk: str | None = None):
        """Query runtime for one edited link without running full canvas refresh."""
        topology = self.get_object()
        payload = request.data or {}
        link_payload = payload.get("link") or {}
        nodes_payload = payload.get("nodes")
        if not isinstance(link_payload, dict) or not link_payload:
            raise DRFValidationError({"link": ["link 必须是对象"]})
        if nodes_payload is not None and not isinstance(nodes_payload, list):
            raise DRFValidationError({"nodes": ["nodes 必须是数组"]})
        adapter = _adapter_for(topology)
        try:
            response = NetworkTopologyRuntimeService.build_link_runtime_preview(
                topology,
                adapter,
                link_payload,
                nodes_payload=nodes_payload,
            )
        except WeOpsTopologyAdapterError as exc:
            return self._adapter_error_response(exc)
        data = response.get("data", response) if isinstance(response, dict) else response
        return Response(data)

    @staticmethod
    def _decode_node_ref(node_ref: str | None) -> dict | None:
        """Decode a URL-encoded JSON node_ref coming from the frontend.

        The frontend uses ``encodeURIComponent(JSON.stringify(ref))`` to
        build the path segment; we reverse it with urllib's
        ``unquote`` + ``json.loads`` so the proxy endpoint accepts the
        same shape the React client sends. Returns ``None`` on parse
        error so the caller can raise a structured 400.
        """
        if not node_ref:
            return None
        try:
            from urllib.parse import unquote

            decoded = unquote(node_ref)
            parsed = json.loads(decoded)
        except (ValueError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None
