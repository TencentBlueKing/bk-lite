"""基线列表 archs 必须复用 view 已预取的补丁 OS 详情，避免随要求数线性查询。"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory

from apps.patch_mgmt.constants import OSType
from apps.patch_mgmt.models import (
    BaselineRequirement,
    LinuxPatchDetail,
    Patch,
    PatchBaseline,
    WindowsPatchDetail,
)
from apps.patch_mgmt.serializers.baseline import (
    PatchBaselineDetailSerializer,
    PatchBaselineListSerializer,
)

EXPECTED_ARCHS = ["arm64", "x64", "x86_64"]
VIEW_PREFETCH = (
    "requirements__patch__windows_detail",
    "requirements__patch__linux_detail",
    "requirements__patch__sources",
)


def _normalized_sql(sql: str) -> str:
    return sql.lower().replace('"', "").replace("`", "")


def _os_detail_row_lookups(queries) -> list[str]:
    """逐条加载 OneToOne 详情的查询；预取 IN 或 requirement JOIN 不算逐条。"""
    hits = []
    for query in queries:
        sql = _normalized_sql(query["sql"])
        for table in ("patch_linux_detail", "patch_windows_detail"):
            if f"from {table}" not in sql:
                continue
            if " in (" in sql or " in(" in sql:
                continue
            hits.append(query["sql"])
    return hits


def _requirement_patch_join_queries(queries) -> list[str]:
    hits = []
    for query in queries:
        sql = _normalized_sql(query["sql"])
        if "patch_baseline_requirement" in sql and "patch_patch" in sql:
            hits.append(query["sql"])
    return hits


def _requirement_os_detail_join_queries(queries) -> list[str]:
    hits = []
    for query in queries:
        sql = _normalized_sql(query["sql"])
        if (
            "patch_baseline_requirement" in sql
            and "patch_windows_detail" in sql
            and "patch_linux_detail" in sql
        ):
            hits.append(query["sql"])
    return hits


def _create_linux_patch(title: str, architectures: list[str] | None):
    patch = Patch.objects.create(title=title, os_type=OSType.LINUX, team=[1])
    if architectures is not None:
        LinuxPatchDetail.objects.create(
            patch=patch,
            pkg_name=title,
            architectures=architectures,
        )
    return patch


def _create_windows_patch(title: str, kb_number: str, architectures: list[str]):
    patch = Patch.objects.create(title=title, os_type=OSType.WINDOWS, team=[1])
    WindowsPatchDetail.objects.create(
        patch=patch,
        kb_number=kb_number,
        architectures=architectures,
    )
    return patch


def _add_mixed_requirements(baseline: PatchBaseline, suffix: str) -> None:
    linux_a = _create_linux_patch(f"openssl-{suffix}", ["x86_64"])
    windows = _create_windows_patch(f"kb-{suffix}", f"KB5428{suffix}", ["x64", "arm64"])
    linux_dup = _create_linux_patch(f"curl-{suffix}", ["x86_64"])
    linux_missing = _create_linux_patch(f"missing-{suffix}", None)
    for patch in (linux_a, windows, linux_dup, linux_missing):
        BaselineRequirement.objects.create(baseline=baseline, patch=patch)


def _create_baseline_with_requirements(name: str, suffix: str) -> PatchBaseline:
    baseline = PatchBaseline.objects.create(name=name, os_type=OSType.LINUX, team=[1])
    _add_mixed_requirements(baseline, suffix)
    return baseline


def _prefetched_baselines():
    return PatchBaseline.objects.prefetch_related(*VIEW_PREFETCH)


def _serializer_context(authenticated_user):
    authenticated_user.is_superuser = True
    request = APIRequestFactory().get("/api/v1/patch_mgmt/api/baseline/", {"page_size": -1})
    request.COOKIES["current_team"] = "1"
    request.user = authenticated_user
    return {"request": request}


def _serialize_list(authenticated_user):
    return PatchBaselineListSerializer(
        _prefetched_baselines(),
        many=True,
        context=_serializer_context(authenticated_user),
    ).data


def _list_item(payload, baseline_id: int) -> dict:
    return next(item for item in payload if item["id"] == baseline_id)


def _capture_list(authenticated_user, baseline: PatchBaseline):
    with CaptureQueriesContext(connection) as captured:
        item = _list_item(_serialize_list(authenticated_user), baseline.id)
    return captured, item


@pytest.mark.django_db
def test_baseline_list_archs_sorted_unique_and_skips_missing_detail(authenticated_user):
    baseline = _create_baseline_with_requirements("archs-semantics", "1001")

    assert _list_item(_serialize_list(authenticated_user), baseline.id)["archs"] == EXPECTED_ARCHS


@pytest.mark.django_db
def test_baseline_list_os_detail_queries_do_not_grow_with_requirements(authenticated_user):
    baseline = _create_baseline_with_requirements("archs-scale", "2001")

    captured_four, item_four = _capture_list(authenticated_user, baseline)
    lookups_four = _os_detail_row_lookups(captured_four)
    joins_four = _requirement_patch_join_queries(captured_four)

    _add_mixed_requirements(baseline, "2002")
    captured_eight, item_eight = _capture_list(authenticated_user, baseline)
    lookups_eight = _os_detail_row_lookups(captured_eight)
    joins_eight = _requirement_patch_join_queries(captured_eight)

    assert item_four["archs"] == EXPECTED_ARCHS
    assert item_eight["archs"] == EXPECTED_ARCHS
    assert lookups_four == [], lookups_four
    assert lookups_eight == [], lookups_eight
    assert joins_four == [], joins_four
    assert joins_eight == [], joins_eight


@pytest.mark.django_db
def test_baseline_list_archs_for_multiple_baselines_without_row_lookups(authenticated_user):
    first = _create_baseline_with_requirements("archs-multi-a", "3001")
    second = _create_baseline_with_requirements("archs-multi-b", "3002")

    with CaptureQueriesContext(connection) as captured:
        payload = _serialize_list(authenticated_user)

    assert _list_item(payload, first.id)["archs"] == EXPECTED_ARCHS
    assert _list_item(payload, second.id)["archs"] == EXPECTED_ARCHS
    assert _os_detail_row_lookups(captured) == []
    assert _requirement_patch_join_queries(captured) == []


@pytest.mark.django_db
def test_baseline_retrieve_archs_reuses_prefetched_os_details(authenticated_user):
    baseline = _create_baseline_with_requirements("archs-retrieve", "4001")

    with CaptureQueriesContext(connection) as captured:
        payload = PatchBaselineDetailSerializer(
            _prefetched_baselines().get(pk=baseline.id),
            context=_serializer_context(authenticated_user),
        ).data

    assert payload["archs"] == EXPECTED_ARCHS
    assert _os_detail_row_lookups(captured) == []
    assert _requirement_patch_join_queries(captured) == []


@pytest.mark.django_db
def test_get_archs_without_prefetch_joins_os_details_once():
    baseline = _create_baseline_with_requirements("archs-fallback", "5001")
    fresh = PatchBaseline.objects.get(pk=baseline.id)
    serializer = PatchBaselineListSerializer.__new__(PatchBaselineListSerializer)
    serializer._context = {}

    with CaptureQueriesContext(connection) as captured:
        archs = serializer.get_archs(fresh)

    assert archs == EXPECTED_ARCHS
    assert _os_detail_row_lookups(captured) == []
    assert len(_requirement_os_detail_join_queries(captured)) == 1
