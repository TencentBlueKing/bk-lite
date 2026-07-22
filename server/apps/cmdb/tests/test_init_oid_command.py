from io import StringIO
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

import apps.cmdb.management.commands.init_oid as init_oid_command
from apps.cmdb.models import OidMapping
from apps.cmdb.services.oid_catalog import (
    OidCatalogError,
    OidSyncResult,
    load_oid_catalog,
)


pytestmark = pytest.mark.django_db


def _run(*args):
    output = StringIO()
    call_command("init_oid", *args, stdout=output, stderr=output)
    return output.getvalue()


def _create_mapping(oid, *, built_in=True, model="legacy"):
    return OidMapping.objects.create(
        oid=oid,
        model=model,
        brand="Legacy",
        device_type="switch",
        built_in=built_in,
    )


def test_default_command_syncs_catalog_into_nonempty_database():
    _create_mapping("1.3.6.1.4.1.99999.1")

    output = _run()

    assert OidMapping.objects.filter(built_in=True).count() > 1
    assert "新增=" in output
    assert OidMapping.objects.filter(oid="1.3.6.1.4.1.99999.1").exists()


def test_dry_run_reports_without_writes():
    before = OidMapping.objects.count()

    output = _run("--dry-run")

    assert OidMapping.objects.count() == before
    assert "DRY-RUN" in output


def test_force_never_deletes_stale_builtin():
    stale = _create_mapping("1.3.6.1.4.1.99999.2")

    output = _run("--force")

    assert OidMapping.objects.filter(pk=stale.pk).exists()
    assert "--force 已改为安全全量比较，不会删除内置记录" in output


def test_catalog_error_is_exposed_as_stable_command_error(monkeypatch):
    monkeypatch.setattr(
        init_oid_command,
        "load_oid_catalog",
        lambda: (_ for _ in ()).throw(OidCatalogError("OID_CATALOG_INVALID")),
        raising=False,
    )

    with pytest.raises(CommandError, match="OID_CATALOG_INVALID"):
        _run()


def test_unexpected_catalog_failure_does_not_leak_details(monkeypatch):
    def fail_sync(*args, **kwargs):
        raise RuntimeError("credential=secret")

    logger_error = Mock()
    monkeypatch.setattr(init_oid_command, "sync_oid_catalog", fail_sync, raising=False)
    monkeypatch.setattr(init_oid_command.logger, "error", logger_error, raising=False)

    with pytest.raises(CommandError, match="OID_SYNC_FAILED") as exc_info:
        _run()

    assert "credential=secret" not in str(exc_info.value)
    assert logger_error.call_args_list == [(("OID_SYNC_FAILED",), {})]


def test_second_run_is_idempotent():
    _run()

    output = _run()

    assert "新增=0, 更新=0" in output


def test_custom_override_is_preserved_and_reported():
    entry = next(iter(load_oid_catalog().values()))
    custom = _create_mapping(entry.oid, built_in=False, model="custom-model")

    output = _run()

    custom.refresh_from_db()
    assert custom.model == "custom-model"
    assert custom.built_in is False
    assert "用户覆盖=1" in output


def test_dry_run_force_is_non_destructive_and_reports_compatibility_notice():
    _create_mapping("1.3.6.1.4.1.99999.3")
    before = list(OidMapping.objects.values_list("pk", "oid", "model", "built_in"))

    output = _run("--dry-run", "--force")

    assert list(OidMapping.objects.values_list("pk", "oid", "model", "built_in")) == before
    assert "DRY-RUN" in output
    assert "--force 已改为安全全量比较，不会删除内置记录" in output
