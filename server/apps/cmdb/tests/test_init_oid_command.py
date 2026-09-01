"""init_oid 管理命令。

batch_init 每次启动都会调用 init_oid：built_in=True 的目录行会被重置为目录值。
同一 OID 的 POST 会被 API 拒绝；用户覆盖只能 UPDATE 已有行并设 built_in=False。
"""
from io import StringIO
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

import apps.cmdb.management.commands.init_oid as init_oid_command
from apps.cmdb.models import OidMapping
from apps.cmdb.services.oid_catalog import OidCatalogEntry, OidCatalogError, OidSyncCreate, OidSyncResult, OidSyncUpdate, load_oid_catalog

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


def test_default_command_outputs_exact_five_category_summary_only(monkeypatch):
    result = OidSyncResult(
        created=1,
        updated=1,
        unchanged=4,
        custom_override_oids=("1.3.6.1.4.1.9.1.20",),
        stale_builtin_oids=("1.3.6.1.4.1.9.1.30",),
        created_entries=(
            OidSyncCreate(
                oid="1.3.6.1.4.1.9.1.10",
                model="new-switch",
                brand="Cisco",
                device_type="switch",
            ),
        ),
        updated_entries=(
            OidSyncUpdate(
                oid="1.3.6.1.4.1.9.1.2",
                old_model="old-model",
                new_model="new-model",
                old_brand="Legacy",
                new_brand="Cisco",
                old_device_type="switch",
                new_device_type="router",
            ),
        ),
    )
    monkeypatch.setattr(init_oid_command, "load_oid_catalog", lambda: {})
    monkeypatch.setattr(init_oid_command, "sync_oid_catalog", lambda entries, dry_run: result)

    output = _run()

    assert output == ("SOID同步完成: 新增=1, 更新=1, 未变化=4, 用户覆盖=1, 目录外遗留=1\n")


def test_dry_run_reports_complete_diffs_without_writes(monkeypatch):
    update_oid = "1.3.6.1.4.1.9.1.2"
    create_oid = "1.3.6.1.4.1.9.1.10"
    custom_oid = "1.3.6.1.4.1.9.1.20"
    stale_oid = "1.3.6.1.4.1.9.1.30"
    _create_mapping(update_oid, model="old-model")
    _create_mapping(custom_oid, built_in=False, model="custom-model")
    _create_mapping(stale_oid, model="stale-model")
    entries = {
        oid: OidCatalogEntry(
            oid=oid,
            model=model,
            brand=brand,
            device_type=device_type,
            source_id="test-source",
            verification="verified",
        )
        for oid, model, brand, device_type in (
            (update_oid, "new-model", "Cisco", "router"),
            (create_oid, "new-switch", "Cisco", "switch"),
            (custom_oid, "catalog-model", "Cisco", "firewall"),
        )
    }
    before = list(OidMapping.objects.order_by("oid").values_list("pk", "oid", "model", "brand", "device_type", "built_in"))
    monkeypatch.setattr(init_oid_command, "load_oid_catalog", lambda: entries)

    output = _run("--dry-run")

    assert list(OidMapping.objects.order_by("oid").values_list("pk", "oid", "model", "brand", "device_type", "built_in")) == before
    assert output == (
        "DRY-RUN SOID同步完成: 新增=1, 更新=1, 未变化=0, 用户覆盖=1, "
        "目录外遗留=1\n"
        f"新增 OID {create_oid}: brand=Cisco, model=new-switch, device_type=switch\n"
        f"更新 OID {update_oid}: brand=Legacy -> Cisco, model=old-model -> new-model, "
        "device_type=switch -> router\n"
        f"用户覆盖 OID {custom_oid}\n"
        f"目录外遗留 OID {stale_oid}\n"
    )


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
    # 用户覆盖只能 UPDATE 已有行并设 built_in=False；启动期同步不得改写。
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
