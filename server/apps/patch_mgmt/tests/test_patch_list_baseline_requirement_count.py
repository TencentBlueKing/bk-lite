"""补丁列表 baseline_requirement_count 去 N+1 与计数契约。

补丁库 URL 加载会 import apps.node_mgmt.models.Node，相关 pytest 包装器
需要据此把 node_mgmt 列入 INSTALL_APPS。
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status

from apps.patch_mgmt.constants import OSType, PatchSourceType
from apps.patch_mgmt.models import (
    BaselineRequirement,
    Patch,
    PatchBaseline,
    PatchSource,
)

PATCH_URL = "/api/v1/patch_mgmt/api/patch/"
REQUIREMENT_TABLE = "patch_baseline_requirement"


def _view_client(api_client, authenticated_user):
    authenticated_user.is_superuser = False
    authenticated_user.roles = []
    authenticated_user.permission = {"patch": {"patch-View"}}
    api_client.cookies["current_team"] = "1"
    return api_client


def _per_row_requirement_counts(queries):
    """RelatedManager.count() 产生的逐行 COUNT，不含列表注解里的聚合。"""
    matched = []
    for query in queries:
        normalized = " ".join(query["sql"].lower().split())
        if REQUIREMENT_TABLE not in normalized or "count(" not in normalized:
            continue
        if "where" in normalized and "patch_id" in normalized and "group by" not in normalized:
            matched.append(query["sql"])
    return matched


def _list_items(response):
    payload = response.data
    if isinstance(payload, dict) and "items" in payload:
        return payload["items"]
    return list(payload)


def _seed_reference_matrix():
    source_a = PatchSource.objects.create(
        name="apt-a",
        source_type=PatchSourceType.APT_REPO,
        url="https://a.example.com/ubuntu",
        team=[1],
    )
    source_b = PatchSource.objects.create(
        name="apt-b",
        source_type=PatchSourceType.APT_REPO,
        url="https://b.example.com/ubuntu",
        team=[1],
    )
    zero_ref = Patch.objects.create(title="zero-ref", os_type=OSType.LINUX, team=[1])
    one_ref = Patch.objects.create(title="one-ref", os_type=OSType.LINUX, team=[1])
    multi_baseline = Patch.objects.create(
        title="multi-baseline", os_type=OSType.LINUX, team=[1]
    )
    multi_source = Patch.objects.create(
        title="multi-source", os_type=OSType.LINUX, team=[1]
    )
    multi_source.sources.add(source_a, source_b)

    baseline_a = PatchBaseline.objects.create(
        name="baseline-a", os_type=OSType.LINUX, team=[1]
    )
    baseline_b = PatchBaseline.objects.create(
        name="baseline-b", os_type=OSType.LINUX, team=[1]
    )
    BaselineRequirement.objects.create(baseline=baseline_a, patch=one_ref)
    BaselineRequirement.objects.create(baseline=baseline_a, patch=multi_baseline)
    BaselineRequirement.objects.create(baseline=baseline_b, patch=multi_baseline)
    BaselineRequirement.objects.create(baseline=baseline_a, patch=multi_source)

    expected = {
        zero_ref.id: 0,
        one_ref.id: 1,
        multi_baseline.id: 2,
        multi_source.id: 1,
    }
    return expected, multi_source


def _assert_counts(items, expected):
    by_id = {item["id"]: item["baseline_requirement_count"] for item in items}
    for patch_id, count in expected.items():
        assert patch_id in by_id
        assert by_id[patch_id] == count
        assert isinstance(by_id[patch_id], int)
        assert by_id[patch_id] >= 0


@pytest.mark.django_db
def test_patch_list_avoids_per_row_baseline_requirement_counts(
    api_client, authenticated_user
):
    expected, _ = _seed_reference_matrix()
    for index in range(4):
        extra = Patch.objects.create(
            title=f"extra-small-{index}", os_type=OSType.LINUX, team=[1]
        )
        expected[extra.id] = 0

    client = _view_client(api_client, authenticated_user)

    with CaptureQueriesContext(connection) as small_ctx:
        small_response = client.get(PATCH_URL, {"page_size": -1})
    assert small_response.status_code == status.HTTP_200_OK
    small_items = _list_items(small_response)
    _assert_counts(small_items, expected)
    small_row_counts = _per_row_requirement_counts(small_ctx.captured_queries)
    assert len(small_items) == 8
    assert len(small_row_counts) <= 1

    for index in range(8):
        extra = Patch.objects.create(
            title=f"extra-large-{index}", os_type=OSType.LINUX, team=[1]
        )
        expected[extra.id] = 0

    with CaptureQueriesContext(connection) as large_ctx:
        large_response = client.get(PATCH_URL, {"page_size": -1})
    assert large_response.status_code == status.HTTP_200_OK
    large_items = _list_items(large_response)
    _assert_counts(large_items, expected)
    large_row_counts = _per_row_requirement_counts(large_ctx.captured_queries)
    assert len(large_items) == 16
    assert len(large_row_counts) <= 1
    assert len(large_row_counts) - len(small_row_counts) < 8


@pytest.mark.django_db
def test_patch_list_paginated_and_unbounded_counts_match(
    api_client, authenticated_user
):
    expected, _ = _seed_reference_matrix()
    client = _view_client(api_client, authenticated_user)

    with CaptureQueriesContext(connection) as page_ctx:
        page_response = client.get(PATCH_URL, {"page": 1, "page_size": 2})
    assert page_response.status_code == status.HTTP_200_OK
    page_items = _list_items(page_response)
    assert page_response.data["count"] == 4
    assert len(page_items) == 2
    page_expected = {item["id"]: expected[item["id"]] for item in page_items}
    _assert_counts(page_items, page_expected)
    assert len(_per_row_requirement_counts(page_ctx.captured_queries)) <= 1

    unbounded = client.get(PATCH_URL, {"page_size": -1})
    assert unbounded.status_code == status.HTTP_200_OK
    _assert_counts(_list_items(unbounded), expected)


@pytest.mark.django_db
def test_source_filter_does_not_inflate_baseline_requirement_count(
    api_client, authenticated_user
):
    expected, multi_source = _seed_reference_matrix()
    client = _view_client(api_client, authenticated_user)

    response = client.get(
        PATCH_URL,
        {"page_size": -1, "source_type": PatchSourceType.APT_REPO},
    )
    assert response.status_code == status.HTTP_200_OK
    items = _list_items(response)
    assert [item["id"] for item in items] == [multi_source.id]
    assert items[0]["baseline_requirement_count"] == expected[multi_source.id]


@pytest.mark.django_db
def test_patch_retrieve_returns_same_baseline_requirement_count(
    api_client, authenticated_user
):
    expected, multi_source = _seed_reference_matrix()
    client = _view_client(api_client, authenticated_user)

    response = client.get(f"{PATCH_URL}{multi_source.id}/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["baseline_requirement_count"] == expected[multi_source.id]
