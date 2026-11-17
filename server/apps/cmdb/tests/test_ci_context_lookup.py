"""CI 上下文旁路表：组织点查和待重算入队。不访问图。"""

import pytest
from django.db import IntegrityError, transaction

from apps.cmdb.models.ci_context import CmdbCiContext, CmdbCiContextPending
from apps.cmdb.services.ci_context import lookup_ci_context, schedule_ci_context_pending
from apps.cmdb.services.ci_context_policy import CONTEXT_APPLICATION

pytestmark = pytest.mark.django_db


def _row(**overrides):
    data = dict(
        ci_uuid="host-1",
        context=CONTEXT_APPLICATION,
        root_uuid="app-a",
        root_model="application",
        ci_model="host",
        ip_addr="10.0.0.1",
        organization=[1, 2],
        system_uuid=None,
        layer=1,
        via_uuid=None,
        model_asst_id="application_run_host",
        payload={},
    )
    data.update(overrides)
    return CmdbCiContext.objects.create(**data)


def test_lookup_requires_organization_even_when_rows_exist():
    _row()

    assert lookup_ci_context([], inst_uuids=["host-1"]) == {}
    assert lookup_ci_context(None, inst_uuids=["host-1"]) == {}


def test_organization_list_overlap_filters_rows():
    _row(organization=[1, 2])

    found = lookup_ci_context([1], inst_uuids=[" host-1 ", "", None])

    assert list(found) == ["host-1"]
    row = found["host-1"][0]
    assert row["organization"] == [1, 2]
    assert row["ci_uuid"] == "host-1"
    assert row["context"] == CONTEXT_APPLICATION
    assert row["root_uuid"] == "app-a"
    assert row["root_model"] == "application"
    assert row["ci_model"] == "host"
    assert row["ip_addr"] == "10.0.0.1"
    assert row["system_uuid"] is None
    assert row["layer"] == 1
    assert row["via_uuid"] is None
    assert row["model_asst_id"] == "application_run_host"
    assert row["payload"] == {}
    assert lookup_ci_context([9], inst_uuids=["host-1"]) == {}


def test_same_ci_memberships_are_ordered_by_root_uuid():
    _row(root_uuid="app-b", organization=[1])
    _row(root_uuid="app-a", organization=[1])

    found = lookup_ci_context([1], inst_uuids=["host-1"])

    assert [item["root_uuid"] for item in found["host-1"]] == ["app-a", "app-b"]


def test_ip_lookup_requires_matching_model():
    _row(ci_uuid="host-1", ci_model="host", ip_addr="10.0.0.1", root_uuid="app-a", organization=[1])
    _row(ci_uuid="mysql-1", ci_model="mysql", ip_addr="10.0.0.1", root_uuid="app-a", organization=[1])

    found = lookup_ci_context([1], ip_addrs=["10.0.0.1"], model_id="host")

    assert list(found) == ["host-1"]
    assert found["host-1"][0]["ci_model"] == "host"
    assert "10.0.0.1" not in found
    assert lookup_ci_context([1], ip_addrs=["10.0.0.1"], model_id="redis") == {}
    assert lookup_ci_context([1], ip_addrs=["10.0.0.1"], model_id=" ") == {}
    assert lookup_ci_context([1], ip_addrs=["10.0.0.1"]) == {}


def test_uuid_and_ip_filters_are_unioned_and_keyed_by_ci_uuid():
    _row(ci_uuid="host-1", ci_model="host", ip_addr="10.0.0.1", root_uuid="app-b", organization=[1])
    _row(ci_uuid="host-1", ci_model="host", ip_addr="10.0.0.1", root_uuid="app-a", organization=[1])
    _row(ci_uuid="host-2", ci_model="host", ip_addr="10.0.0.2", root_uuid="app-c", organization=[1])

    found = lookup_ci_context([1], inst_uuids=["host-2"], ip_addrs=["10.0.0.1"], model_id="host")

    assert set(found) == {"host-1", "host-2"}
    assert [item["root_uuid"] for item in found["host-1"]] == ["app-a", "app-b"]


def test_lookup_without_uuid_or_ip_returns_empty():
    _row(organization=[1])

    assert lookup_ci_context([1]) == {}


def test_default_context_excludes_other_contexts():
    _row(context=CONTEXT_APPLICATION, root_uuid="app-a", organization=[1])
    _row(context="other", root_uuid="app-z", organization=[1])

    found = lookup_ci_context([1], inst_uuids=["host-1"])

    assert [item["context"] for item in found["host-1"]] == [CONTEXT_APPLICATION]


def test_schedule_root_uuids_trims_and_dedups():
    schedule_ci_context_pending(root_uuids=["app-1", " app-1 ", "", None, "app-2"])
    schedule_ci_context_pending(root_uuids=["app-1", " app-1 ", "", None, "app-2"])

    rows = list(CmdbCiContextPending.objects.order_by("root_uuid"))
    assert [(row.root_uuid, row.model_asst_id, row.ci_uuid) for row in rows] == [
        ("app-1", None, None),
        ("app-2", None, None),
    ]


def test_schedule_model_asst_ids_trims_and_dedups():
    schedule_ci_context_pending(model_asst_ids=["asst-1", " asst-1 ", "", None, "asst-2"])
    schedule_ci_context_pending(model_asst_ids=["asst-1"])

    rows = list(CmdbCiContextPending.objects.order_by("model_asst_id"))
    assert [(row.root_uuid, row.model_asst_id, row.ci_uuid) for row in rows] == [
        (None, "asst-1", None),
        (None, "asst-2", None),
    ]


def test_schedule_ci_uuids_trims_and_dedups():
    schedule_ci_context_pending(ci_uuids=["host-1", " host-1 ", "", None, "host-2"])
    schedule_ci_context_pending(ci_uuids=["host-2"])

    rows = list(CmdbCiContextPending.objects.order_by("ci_uuid"))
    assert [(row.root_uuid, row.model_asst_id, row.ci_uuid) for row in rows] == [
        (None, None, "host-1"),
        (None, None, "host-2"),
    ]


def test_schedule_three_kinds_creates_one_row_each():
    schedule_ci_context_pending(root_uuids=["app-1"], model_asst_ids=["asst-1"], ci_uuids=["host-1"])

    assert CmdbCiContextPending.objects.count() == 3
    assert CmdbCiContextPending.objects.filter(root_uuid="app-1", model_asst_id__isnull=True, ci_uuid__isnull=True).exists()
    assert CmdbCiContextPending.objects.filter(model_asst_id="asst-1", root_uuid__isnull=True, ci_uuid__isnull=True).exists()
    assert CmdbCiContextPending.objects.filter(ci_uuid="host-1", root_uuid__isnull=True, model_asst_id__isnull=True).exists()


def test_empty_schedule_writes_nothing():
    schedule_ci_context_pending()
    schedule_ci_context_pending(root_uuids=["", None, "  "], model_asst_ids=[], ci_uuids=None)

    assert CmdbCiContextPending.objects.count() == 0


def test_pending_row_rejects_more_or_less_than_one_target():
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CmdbCiContextPending.objects.create(root_uuid="app-1", ci_uuid="host-1")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CmdbCiContextPending.objects.create()

    assert CmdbCiContextPending.objects.count() == 0
