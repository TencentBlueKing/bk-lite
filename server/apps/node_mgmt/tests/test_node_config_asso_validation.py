# -*- coding: utf-8 -*-
"""
Issue #3621: get_node_config_asso 未校验 cloud_region_id 必填，缺失时 KeyError → HTTP 500

验证：请求体缺少 cloud_region_id 时应返回 HTTP 400，而非 500 KeyError。
"""
import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.node_mgmt.views import node as node_view


def _build_admin_user():
    return User(
        username="test-user-3621",
        domain="domain.com",
        locale="en",
        is_superuser=True,
        roles=["admin"],
        group_list=[{"id": 1, "name": "Team"}],
    )


@pytest.mark.django_db
def test_issue_3621_missing_cloud_region_id_returns_400():
    """
    缺少 cloud_region_id 时，接口应返回 HTTP 400，而非因 KeyError 导致 HTTP 500。
    验证标准：revert 修复（恢复 request.data["cloud_region_id"]）后本测试应 fail（KeyError）。
    """
    factory = APIRequestFactory()
    request = factory.post(
        "/node_config/node_config_asso/",
        data={},
        format="json",
    )
    force_authenticate(request, user=_build_admin_user())

    view = node_view.NodeViewSet.as_view({"post": "get_node_config_asso"})
    response = view(request)

    assert response.status_code == 400, (
        f"缺少 cloud_region_id 时期望 HTTP 400，实际得到 {response.status_code}"
    )
    body = json.loads(response.content)
    assert body["result"] is False
    assert "cloud_region_id" in body["message"]


@pytest.mark.django_db
def test_issue_3621_null_cloud_region_id_returns_400():
    """
    cloud_region_id 显式为 null 时，同样应返回 HTTP 400。
    """
    factory = APIRequestFactory()
    request = factory.post(
        "/node_config/node_config_asso/",
        data={"cloud_region_id": None},
        format="json",
    )
    force_authenticate(request, user=_build_admin_user())

    view = node_view.NodeViewSet.as_view({"post": "get_node_config_asso"})
    response = view(request)

    assert response.status_code == 400
    body = json.loads(response.content)
    assert body["result"] is False


@pytest.mark.django_db
def test_issue_3621_with_cloud_region_id_proceeds_normally(monkeypatch):
    """
    提供合法 cloud_region_id 时，接口正常执行（返回 200 或无 KeyError）。
    """
    # patch get_authorized_node_queryset 返回空 queryset，避免真实 DB 依赖
    from apps.node_mgmt.models import Node

    monkeypatch.setattr(
        node_view,
        "get_authorized_node_queryset",
        lambda request, *args, **kwargs: Node.objects.none(),
    )

    factory = APIRequestFactory()
    request = factory.post(
        "/node_config/node_config_asso/",
        data={"cloud_region_id": 1},
        format="json",
    )
    force_authenticate(request, user=_build_admin_user())

    view = node_view.NodeViewSet.as_view({"post": "get_node_config_asso"})
    response = view(request)

    # 有 cloud_region_id 时不应因 KeyError 崩溃
    assert response.status_code == 200
