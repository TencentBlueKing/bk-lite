import importlib

import pytest
from django.apps import apps as django_apps


def _run_forwards():
    migration = importlib.import_module("apps.operation_analysis.migrations.0030_clear_default_only_builtin_datasource_groups")
    migration.forwards(django_apps, None)


@pytest.mark.django_db
def test_forwards_clears_default_only_and_keeps_custom_allowlist():
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
    from apps.system_mgmt.models.user import Group

    default, _ = Group.objects.get_or_create(name="Default", parent_id=0)
    other, _ = Group.objects.get_or_create(name="Other", parent_id=0)

    only_default = DataSourceAPIModel.objects.create(
        name="seed",
        rest_api="seed/api",
        groups=[default.id],
        is_build_in=True,
        build_in_key="seed",
    )
    mixed = DataSourceAPIModel.objects.create(
        name="mixed",
        rest_api="mixed/api",
        groups=[default.id, other.id],
        is_build_in=True,
        build_in_key="mixed",
    )
    custom = DataSourceAPIModel.objects.create(
        name="custom",
        rest_api="custom/api",
        groups=[default.id],
        is_build_in=False,
    )
    _run_forwards()
    only_default.refresh_from_db()
    mixed.refresh_from_db()
    custom.refresh_from_db()
    assert only_default.groups == []
    assert mixed.groups == [default.id, other.id]
    assert custom.groups == [default.id]


@pytest.mark.django_db
def test_forwards_empty_builtin_groups_stay_empty():
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default", parent_id=0)
    empty_builtin = DataSourceAPIModel.objects.create(
        name="already-global",
        rest_api="already/global",
        groups=[],
        is_build_in=True,
        build_in_key="already-global",
    )
    _run_forwards()
    empty_builtin.refresh_from_db()
    assert empty_builtin.groups == []


@pytest.mark.django_db
def test_forwards_is_idempotent_and_preserves_mixed_order():
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
    from apps.system_mgmt.models.user import Group

    default, _ = Group.objects.get_or_create(name="Default", parent_id=0)
    other, _ = Group.objects.get_or_create(name="Other", parent_id=0)
    only_default = DataSourceAPIModel.objects.create(
        name="seed-twice",
        rest_api="seed-twice/api",
        groups=[default.id],
        is_build_in=True,
        build_in_key="seed-twice",
    )
    mixed = DataSourceAPIModel.objects.create(
        name="mixed-order",
        rest_api="mixed-order/api",
        groups=[other.id, default.id],
        is_build_in=True,
        build_in_key="mixed-order",
    )
    other_only = DataSourceAPIModel.objects.create(
        name="other-only",
        rest_api="other-only/api",
        groups=[other.id],
        is_build_in=True,
        build_in_key="other-only",
    )
    _run_forwards()
    _run_forwards()
    only_default.refresh_from_db()
    mixed.refresh_from_db()
    other_only.refresh_from_db()
    assert only_default.groups == []
    assert mixed.groups == [other.id, default.id]
    assert other_only.groups == [other.id]
