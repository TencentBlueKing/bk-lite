import hashlib
import json
from collections import Counter
from dataclasses import replace

import pytest
from django.db import IntegrityError, connection
from django.db.models import QuerySet
from django.utils import timezone

from apps.cmdb.models import OidMapping
from apps.cmdb.services import oid_catalog as oid_catalog_service
from apps.cmdb.services.oid_catalog import (
    SYSTEMOID_METADATA_PATH,
    SYSTEMOID_PATH,
    OidCatalogEntry,
    OidCatalogError,
    load_oid_catalog,
    sync_oid_catalog,
)

DOMESTIC_REQUIRED_FAMILIES = {
    "Huawei": {"switch", "router", "firewall"},
    "H3C": {"switch", "router", "firewall"},
    "Ruijie": {"switch", "router", "firewall"},
    "ZTE": {"switch", "router"},
    "Sangfor": {"firewall", "loadbalance"},
    "Hillstone": {"firewall"},
    "DPtech": {"firewall"},
    "Topsec": {"firewall"},
    "Venustech": {"firewall"},
    "NSFOCUS": {"firewall"},
    "Qi-Anxin": {"firewall"},
}

DOMESTIC_VERIFIED_OIDS = {
    "1.3.6.1.4.1.25506.1.763": ("H3C", "MSR2630", "router"),
    "1.3.6.1.4.1.25506.1.764": ("H3C", "MSR3610AC", "router"),
    "1.3.6.1.4.1.25506.1.765": ("H3C", "MSR3610DC", "router"),
    "1.3.6.1.4.1.25506.1.766": ("H3C", "MSR3620AC", "router"),
    "1.3.6.1.4.1.25506.1.767": ("H3C", "MSR3620DC", "router"),
    "1.3.6.1.4.1.25506.1.768": ("H3C", "MSR3620POE", "router"),
    "1.3.6.1.4.1.25506.1.769": ("H3C", "MSR3640", "router"),
    "1.3.6.1.4.1.25506.1.770": ("H3C", "MSR3660", "router"),
    "1.3.6.1.4.1.25506.1.771": ("H3C", "MSR5660", "router"),
    "1.3.6.1.4.1.25506.1.937": ("H3C", "VSR1000", "router"),
    "1.3.6.1.4.1.25506.1.1260": ("H3C", "MSR810", "router"),
    "1.3.6.1.4.1.25506.1.1472": ("H3C", "MSR3610-X1", "router"),
    "1.3.6.1.4.1.25506.1.2369": ("H3C", "S5590-28T8XC-HI", "switch"),
    "1.3.6.1.4.1.25506.1.2370": ("H3C", "S5590-28S8XC-HI", "switch"),
    "1.3.6.1.4.1.25506.1.2371": ("H3C", "S5590-48T4XC-HI", "switch"),
    "1.3.6.1.4.1.25506.1.2372": ("H3C", "S5590-48S4XC-HI", "switch"),
    "1.3.6.1.4.1.25506.1.2431": ("H3C", "S5590-48T4XC-EI", "switch"),
    "1.3.6.1.4.1.25506.1.2432": ("H3C", "S5590-28T8XC-EI", "switch"),
    "1.3.6.1.4.1.25506.1.2433": ("H3C", "S5590-48S4XC-EI", "switch"),
    "1.3.6.1.4.1.25506.1.2434": ("H3C", "S5590-28S8XC-EI", "switch"),
    "1.3.6.1.4.1.25506.1.2450": ("H3C", "S5500V3-28T8XC-HI", "switch"),
    "1.3.6.1.4.1.25506.1.2451": ("H3C", "S5500V3-28S8XC-HI", "switch"),
    "1.3.6.1.4.1.25506.1.2452": ("H3C", "S5500V3-48T4XC-HI", "switch"),
    "1.3.6.1.4.1.25506.1.2881": ("H3C", "S5538F-EI-D", "switch"),
    "1.3.6.1.4.1.25506.1.2882": ("H3C", "S5554C-EI-D-AC", "switch"),
    "1.3.6.1.4.1.25506.1.2915": ("H3C", "S5590-28P8XC-EI", "switch"),
    "1.3.6.1.4.1.25506.1.2916": ("H3C", "S5590-48P6XC-EI", "switch"),
    "1.3.6.1.4.1.25506.1.3259": ("H3C", "S6530X-48Y8C", "switch"),
    "1.3.6.1.4.1.25506.1.3260": ("H3C", "S6530X-48X8C", "switch"),
    "1.3.6.1.4.1.25506.1.3261": ("H3C", "S6530X-24Y8C", "switch"),
    "1.3.6.1.4.1.25506.1.3262": ("H3C", "S6530X-24X8C", "switch"),
    "1.3.6.1.4.1.4881.250.160": ("Ruijie", "RG-WALL 160E", "firewall"),
    "1.3.6.1.4.1.4881.250.161": ("Ruijie", "RG-WALL 160S", "firewall"),
    "1.3.6.1.4.1.4881.250.1600": ("Ruijie", "RG-WALL 1600E", "firewall"),
    "1.3.6.1.4.1.4881.250.1601": ("Ruijie", "RG-WALL 1600S", "firewall"),
    "1.3.6.1.4.1.28557.1.9": ("Hillstone", "SA2003", "firewall"),
    "1.3.6.1.4.1.28557.1.10": ("Hillstone", "SA2001", "firewall"),
    "1.3.6.1.4.1.28557.1.11": ("Hillstone", "SR320", "firewall"),
    "1.3.6.1.4.1.28557.1.13": ("Hillstone", "SR520", "firewall"),
    "1.3.6.1.4.1.28557.1.17": ("Hillstone", "SA5180", "firewall"),
    "1.3.6.1.4.1.28557.1.18": ("Hillstone", "SA5160", "firewall"),
    "1.3.6.1.4.1.28557.1.22": ("Hillstone", "SG-6000-G6100", "firewall"),
    "1.3.6.1.4.1.28557.1.23": ("Hillstone", "SG-6000-G3100", "firewall"),
    "1.3.6.1.4.1.28557.1.25": ("Hillstone", "SG-6000-M2100", "firewall"),
    "1.3.6.1.4.1.28557.1.31": ("Hillstone", "SG-6000-G2120", "firewall"),
    "1.3.6.1.4.1.28557.1.32": ("Hillstone", "VR5600T", "firewall"),
    "1.3.6.1.4.1.28557.1.33": ("Hillstone", "SG-6000-NAV10", "firewall"),
    "1.3.6.1.4.1.28557.1.35": ("Hillstone", "SG-6000-NAV30", "firewall"),
    "1.3.6.1.4.1.28557.1.36": ("Hillstone", "SG-6000-G2110", "firewall"),
    "1.3.6.1.4.1.28557.1.37": ("Hillstone", "SG-6000-NAV50", "firewall"),
    "1.3.6.1.4.1.28557.1.38": ("Hillstone", "SG-6000-NAV200", "firewall"),
    "1.3.6.1.4.1.28557.1.39": ("Hillstone", "SG-6000-NAV300", "firewall"),
    "1.3.6.1.4.1.28557.1.40": ("Hillstone", "SG-6000-NAV500", "firewall"),
    "1.3.6.1.4.1.28557.1.45": ("Hillstone", "SG-6000-M2105", "firewall"),
    "1.3.6.1.4.1.28557.1.47": ("Hillstone", "SR-320", "firewall"),
    "1.3.6.1.4.1.28557.1.48": ("Hillstone", "SR-520", "firewall"),
    "1.3.6.1.4.1.28557.1.51": ("Hillstone", "SG-6000-M3105", "firewall"),
    "1.3.6.1.4.1.28557.1.52": ("Hillstone", "SC-1000-M3108", "firewall"),
    "1.3.6.1.4.1.28557.1.54": ("Hillstone", "SG-6000-BANFF", "firewall"),
    "1.3.6.1.4.1.28557.1.96": ("Hillstone", "E5660-B", "firewall"),
}

DOMESTIC_TASK_SOURCE_IDS = {
    "h3c-msr-router-rfc1213-r6749",
    "h3c-vsr-router-rfc1213",
    "h3c-s5590-s6530x-mib-6w101",
    "ruijie-rg-wall-vpn-snmp",
    "hillstone-products-mib-v3",
    "hillstone-kb-sysobjectid-viewing",
}

FOREIGN_CATALOG_BRAND_COUNTS = {
    "Cisco": 577,
    "HPE": 82,
    "SynOptics": 64,
    "Enterasys Networks": 1,
    "Nokia": 8,
    "D-Link": 4,
    "Brocade": 66,
    "Alteon": 54,
    "Extreme": 5,
    "Rapid": 26,
    "Giganet": 1,
    "Juniper": 70,
    "F5": 22,
    "Riverstone": 6,
    "Dell": 17,
    "Alcatel-Lucent": 1,
    "Piolink": 1,
    "Fortinet": 5,
    "Aruba": 2,
    "Arista": 3,
    "Palo Alto Networks": 2,
}

INTERNATIONAL_REQUIRED_FAMILIES = {
    "Cisco": {"switch", "router", "firewall"},
    "Juniper": {"switch", "router", "firewall"},
    "HPE": {"switch"},
    "Aruba": {"switch"},
    "Arista": {"switch"},
    "Fortinet": {"firewall"},
    "Palo Alto Networks": {"firewall"},
    "F5": {"loadbalance"},
    "Extreme": {"switch"},
    "Nokia": {"router"},
}

INTERNATIONAL_VERIFIED_OIDS = {
    "1.3.6.1.4.1.9.1.3086": ("Cisco", "C9300X-48HXN", "switch"),
    "1.3.6.1.4.1.9.1.3091": ("Cisco", "Nexus 9348D-GX2A", "switch"),
    "1.3.6.1.4.1.9.1.1935": ("Cisco", "ISR 4431", "router"),
    "1.3.6.1.4.1.9.1.3075": ("Cisco", "ASR 9903", "router"),
    "1.3.6.1.4.1.9.1.3053": ("Cisco", "Firepower 3110", "firewall"),
    "1.3.6.1.4.1.30065.1.3011.7050.2966.4.32.3282": (
        "Arista",
        "DCS-7050DX4-32S",
        "switch",
    ),
    "1.3.6.1.4.1.30065.1.2546.720.2974.48.3282": (
        "Arista",
        "CCS-720DP-48S",
        "switch",
    ),
    "1.3.6.1.4.1.30065.1.3011.7304": ("Arista", "DCS-7304", "switch"),
    "1.3.6.1.4.1.12356.101.1.1000": ("Fortinet", "FortiGate 100F", "firewall"),
    "1.3.6.1.4.1.25461.2.3.54": (
        "Palo Alto Networks",
        "PA-440",
        "firewall",
    ),
    "1.3.6.1.4.1.25461.2.3.29": (
        "Palo Alto Networks",
        "VM-Series",
        "firewall",
    ),
    "1.3.6.1.4.1.12276.1.3.1.1": ("F5", "BIG-IP rSeries R5x00", "loadbalance"),
}

INTERNATIONAL_TASK_SOURCE_IDS = {
    "cisco-products-mib-20250613",
    "arista-products-mib-20260303",
    "fortinet-fortigate-model-mibs-7-4-0",
    "paloalto-pan-products-mib-pan-os-12-1",
    "f5os-rseries-system-settings-1-2-0",
}


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _metadata():
    return {
        "schema_version": 1,
        "catalog_version": "2026.07.22",
        "allowed_device_types": ["switch", "router", "firewall", "loadbalance"],
        "brand_aliases": {"华为": "Huawei"},
        "coverage_gaps": {},
        "coverage_gap_details": {},
        "sources": {
            "huawei-product-mib": {
                "vendor": "Huawei",
                "url": "https://info.support.huawei.com/info-finder/tool/zh/enterprise/mib",
                "document": "Huawei MIB Query",
                "version": "2026-07",
                "verified_at": "2026-07-22",
                "official": True,
                "scope": "product-identity",
            }
        },
    }


def _entry(oid="1.3.6.1.4.1.2011.2.23.968"):
    return {
        "OID": oid,
        "FirstTypeId": "Switch",
        "FirstTypeName": "交换机",
        "SecondTypeId": "HuaweiSwitch",
        "SecondTypeName": "Huawei交换机",
        "model": "S5735S-L8T4S-QA2",
        "brand": "Huawei",
        "source_id": "huawei-product-mib",
        "verification": "verified",
    }


def _catalog_entry(oid, *, model="S5735", brand="Huawei", device_type="switch"):
    return OidCatalogEntry(
        oid=oid,
        model=model,
        brand=brand,
        device_type=device_type,
        source_id="test-source",
        verification="verified",
    )


@pytest.mark.django_db
def test_sync_adds_missing_entry_when_builtin_rows_already_exist():
    OidMapping.objects.create(
        oid="1.3.6.1.4.1.9.1.1208",
        model="old",
        brand="Cisco",
        device_type="switch",
        built_in=True,
    )
    new_oid = "1.3.6.1.4.1.2011.2.23.968"

    result = sync_oid_catalog({new_oid: _catalog_entry(new_oid)})

    assert result.created == 1
    assert OidMapping.objects.get(oid=new_oid).built_in is True


@pytest.mark.django_db
def test_sync_updates_builtin_in_place_but_preserves_custom_override():
    """batch_init/init_oid 每次启动重置 built_in=True；用户覆盖只能 UPDATE 设 built_in=False。
    同一 OID 的 POST 会被 API 拒绝，同步不得改写自定义行。
    """
    builtin = OidMapping.objects.create(
        oid="1.3.6.1.4.1.9.1.1",
        model="old",
        brand="old",
        device_type="router",
        built_in=True,
    )
    custom = OidMapping.objects.create(
        oid="1.3.6.1.4.1.9.1.2",
        model="custom",
        brand="custom",
        device_type="router",
        built_in=False,
    )
    entries = {
        builtin.oid: _catalog_entry(builtin.oid, model="new", brand="Cisco", device_type="switch"),
        custom.oid: _catalog_entry(custom.oid, model="catalog", brand="Cisco", device_type="switch"),
    }

    result = sync_oid_catalog(entries)

    builtin.refresh_from_db()
    custom.refresh_from_db()
    assert (builtin.model, builtin.brand, builtin.device_type, builtin.id) == (
        "new",
        "Cisco",
        "switch",
        builtin.id,
    )
    assert (custom.model, custom.brand, custom.device_type) == (
        "custom",
        "custom",
        "router",
    )
    assert result.custom_override_oids == (custom.oid,)


@pytest.mark.django_db
def test_sync_dry_run_reports_changes_without_writing_database():
    existing_oid = "1.3.6.1.4.1.9.1.1"
    missing_oid = "1.3.6.1.4.1.2011.2.23.968"
    existing = OidMapping.objects.create(
        oid=existing_oid,
        model="old",
        brand="old",
        device_type="router",
        built_in=True,
    )
    entries = {
        existing_oid: _catalog_entry(existing_oid, model="new"),
        missing_oid: _catalog_entry(missing_oid),
    }

    result = sync_oid_catalog(entries, dry_run=True)

    existing.refresh_from_db()
    assert (result.created, result.updated) == (1, 1)
    assert (existing.model, existing.brand, existing.device_type) == (
        "old",
        "old",
        "router",
    )
    assert not OidMapping.objects.filter(oid=missing_oid).exists()


@pytest.mark.django_db
def test_sync_result_exposes_complete_create_and_update_diffs_in_numeric_order():
    update_oids = ("1.3.6.1.4.1.9.1.2", "1.3.6.1.4.1.9.1.11")
    create_oids = ("1.3.6.1.4.1.9.1.3", "1.3.6.1.4.1.9.1.10")
    for oid in reversed(update_oids):
        OidMapping.objects.create(
            oid=oid,
            model=f"old-{oid.rsplit('.', 1)[-1]}",
            brand="old-brand",
            device_type="router",
            built_in=True,
        )

    result = sync_oid_catalog(
        {
            oid: _catalog_entry(
                oid,
                model=f"new-{oid.rsplit('.', 1)[-1]}",
                brand="Fortinet" if oid in update_oids else "Cisco",
                device_type="firewall" if oid in update_oids else "switch",
            )
            for oid in reversed((*update_oids, *create_oids))
        },
        dry_run=True,
    )

    assert [entry.oid for entry in result.created_entries] == list(create_oids)
    assert [entry.oid for entry in result.updated_entries] == list(update_oids)
    assert result.created_entries[0] == (
        oid_catalog_service.OidSyncCreate(
            oid="1.3.6.1.4.1.9.1.3",
            model="new-3",
            brand="Cisco",
            device_type="switch",
        )
    )
    assert result.updated_entries[0] == (
        oid_catalog_service.OidSyncUpdate(
            oid="1.3.6.1.4.1.9.1.2",
            old_model="old-2",
            new_model="new-2",
            old_brand="old-brand",
            new_brand="Fortinet",
            old_device_type="router",
            new_device_type="firewall",
        )
    )


@pytest.mark.django_db
def test_sync_is_idempotent_and_counts_non_custom_entries_as_unchanged():
    unchanged_oid = "1.3.6.1.4.1.9.1.1"
    custom_oid = "1.3.6.1.4.1.9.1.2"
    missing_oid = "1.3.6.1.4.1.2011.2.23.968"
    OidMapping.objects.create(
        oid=unchanged_oid,
        model="S5735",
        brand="Huawei",
        device_type="switch",
        built_in=True,
    )
    OidMapping.objects.create(
        oid=custom_oid,
        model="custom",
        brand="custom",
        device_type="router",
        built_in=False,
    )
    entries = {
        unchanged_oid: _catalog_entry(unchanged_oid),
        custom_oid: _catalog_entry(custom_oid),
        missing_oid: _catalog_entry(missing_oid),
    }

    first = sync_oid_catalog(entries)
    second = sync_oid_catalog(entries)

    assert (first.created, first.updated, first.unchanged) == (1, 0, 1)
    assert (second.created, second.updated, second.unchanged) == (0, 0, 2)
    assert second.custom_override_oids == (custom_oid,)


@pytest.mark.django_db
def test_sync_does_not_refresh_unchanged_builtin_updated_at():
    oid = "1.3.6.1.4.1.9.1.1"
    row = OidMapping.objects.create(
        oid=oid,
        model="S5735",
        brand="Huawei",
        device_type="switch",
        built_in=True,
    )
    original_updated_at = timezone.now().replace(year=2020)
    OidMapping.objects.filter(pk=row.pk).update(updated_at=original_updated_at)

    result = sync_oid_catalog({oid: _catalog_entry(oid)})

    row.refresh_from_db()
    assert result.unchanged == 1
    assert row.updated_at == original_updated_at


@pytest.mark.django_db
def test_sync_reports_but_preserves_stale_builtin_rows():
    stale_oid = "1.3.6.1.4.1.9.1.1"
    current_oid = "1.3.6.1.4.1.9.1.2"
    OidMapping.objects.create(
        oid=stale_oid,
        model="legacy",
        brand="Cisco",
        device_type="switch",
        built_in=True,
    )

    result = sync_oid_catalog({current_oid: _catalog_entry(current_oid)})

    assert result.stale_builtin_oids == (stale_oid,)
    assert OidMapping.objects.filter(oid=stale_oid, built_in=True).exists()


@pytest.mark.django_db(transaction=True)
def test_sync_rolls_back_creates_when_bulk_update_fails(monkeypatch):
    existing_oid = "1.3.6.1.4.1.9.1.1"
    missing_oid = "1.3.6.1.4.1.2011.2.23.968"
    existing = OidMapping.objects.create(
        oid=existing_oid,
        model="old",
        brand="old",
        device_type="router",
        built_in=True,
    )

    def fail_bulk_update(*args, **kwargs):
        raise RuntimeError("bulk update failed")

    monkeypatch.setattr(OidMapping._default_manager, "bulk_update", fail_bulk_update)

    with pytest.raises(RuntimeError, match="bulk update failed"):
        sync_oid_catalog({existing_oid: _catalog_entry(existing_oid, model="new"), missing_oid: _catalog_entry(missing_oid)})

    existing.refresh_from_db()
    assert existing.model == "old"
    assert not OidMapping.objects.filter(oid=missing_oid).exists()


@pytest.mark.django_db(transaction=True)
def test_sync_retries_whole_transaction_and_preserves_concurrent_custom_winner(
    monkeypatch,
):
    catalog_oid = "1.3.6.1.4.1.9.1.1"
    rolled_back_oid = "1.3.6.1.4.1.9.1.2"
    original_sync = oid_catalog_service._sync_oid_catalog
    attempts = []

    def race_then_sync(entries, *, write):
        attempts.append(write)
        if len(attempts) == 1:
            OidMapping.objects.create(
                oid=rolled_back_oid,
                model="must rollback",
                brand="test",
                device_type="router",
                built_in=True,
            )
            raise IntegrityError("simulated unique OID race")
        OidMapping.objects.create(
            oid=catalog_oid,
            model="custom",
            brand="custom",
            device_type="router",
            built_in=False,
        )
        return original_sync(entries, write=write)

    monkeypatch.setattr(oid_catalog_service, "_sync_oid_catalog", race_then_sync)

    result = sync_oid_catalog({catalog_oid: _catalog_entry(catalog_oid)})

    winner = OidMapping.objects.get(oid=catalog_oid)
    assert attempts == [True, True]
    assert (winner.model, winner.brand, winner.device_type, winner.built_in) == (
        "custom",
        "custom",
        "router",
        False,
    )
    assert (result.created, result.updated, result.custom_override_oids) == (
        0,
        0,
        (catalog_oid,),
    )
    assert not OidMapping.objects.filter(oid=rolled_back_oid).exists()


@pytest.mark.django_db(transaction=True)
def test_sync_unique_conflict_retry_is_bounded(monkeypatch):
    oid = "1.3.6.1.4.1.9.1.1"
    attempts = []

    def always_conflict(entries, *, write):
        attempts.append(write)
        raise IntegrityError("persistent unique OID conflict")

    monkeypatch.setattr(oid_catalog_service, "_sync_oid_catalog", always_conflict)

    with pytest.raises(IntegrityError, match="persistent unique OID conflict"):
        sync_oid_catalog({oid: _catalog_entry(oid)})

    assert attempts == [True, True]


@pytest.mark.django_db
def test_sync_result_oids_use_numeric_segment_sorting():
    custom_oids = ["1.3.6.1.4.1.9.1.10", "1.3.6.1.4.1.9.1.2"]
    stale_oids = ["1.3.6.1.4.1.2011.10", "1.3.6.1.4.1.2011.2"]
    for oid in custom_oids:
        OidMapping.objects.create(
            oid=oid,
            model="custom",
            brand="custom",
            device_type="router",
            built_in=False,
        )
    for oid in stale_oids:
        OidMapping.objects.create(
            oid=oid,
            model="legacy",
            brand="legacy",
            device_type="router",
            built_in=True,
        )

    result = sync_oid_catalog({oid: _catalog_entry(oid) for oid in reversed(custom_oids)})

    assert result.custom_override_oids == tuple(reversed(custom_oids))
    assert result.stale_builtin_oids == tuple(reversed(stale_oids))


@pytest.mark.django_db(transaction=True)
def test_sync_write_locks_existing_rows_inside_atomic_but_dry_run_does_not(
    monkeypatch,
):
    oid = "1.3.6.1.4.1.9.1.1"
    OidMapping.objects.create(
        oid=oid,
        model="S5735",
        brand="Huawei",
        device_type="switch",
        built_in=True,
    )
    original_select_for_update = QuerySet.select_for_update
    lock_calls = []

    def record_select_for_update(queryset, *args, **kwargs):
        lock_calls.append(connection.in_atomic_block)
        return original_select_for_update(queryset, *args, **kwargs)

    monkeypatch.setattr(QuerySet, "select_for_update", record_select_for_update)

    sync_oid_catalog({oid: _catalog_entry(oid)}, dry_run=True)
    assert lock_calls == []

    sync_oid_catalog({oid: _catalog_entry(oid)})
    assert lock_calls == [True]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "entries",
    [
        {},
        {
            "1.3.6.1.4.1.9.1.1": replace(
                _catalog_entry("1.3.6.1.4.1.9.1.1"),
                oid="1.3.6.1.4.1.9.1.2",
            )
        },
        {"not-an-oid": _catalog_entry("not-an-oid")},
        {
            "1.3.6.1.4.1.9.1.1": replace(
                _catalog_entry("1.3.6.1.4.1.9.1.1"),
                device_type=["switch"],
            )
        },
        {".".join(["1"] * 33): _catalog_entry(".".join(["1"] * 33))},
        {
            "1.3.6.1.4.1.9.1.1": replace(
                _catalog_entry("1.3.6.1.4.1.9.1.1"),
                model="m" * 129,
            )
        },
        {
            "1.3.6.1.4.1.9.1.1": replace(
                _catalog_entry("1.3.6.1.4.1.9.1.1"),
                brand="b" * 65,
            )
        },
    ],
    ids=[
        "empty",
        "key-mismatch",
        "malformed-oid",
        "non-string-device-type",
        "oid-too-long",
        "model-too-long",
        "brand-too-long",
    ],
)
def test_sync_rejects_invalid_entries_before_reading_database(monkeypatch, entries):
    def fail_database_read(*args, **kwargs):
        raise AssertionError("invalid entries must fail before database access")

    monkeypatch.setattr(OidMapping._default_manager, "all", fail_database_read)

    with pytest.raises(OidCatalogError, match="OID_CATALOG_INVALID"):
        sync_oid_catalog(entries)


def test_load_oid_catalog_returns_normalized_entry(tmp_path):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    oid = "1.3.6.1.4.1.2011.2.23.968"
    _write_json(catalog, {oid: _entry(oid)})
    _write_json(metadata, _metadata())

    entries = load_oid_catalog(catalog, metadata)

    assert entries[oid].brand == "Huawei"
    assert entries[oid].device_type == "switch"
    assert entries[oid].source_id == "huawei-product-mib"


@pytest.mark.parametrize(
    ("key", "stored_oid"),
    [
        (".1.3.6.1.4.1.2011.1", ".1.3.6.1.4.1.2011.1"),
        ("1.3.6.1.4.1.2011.1 ", "1.3.6.1.4.1.2011.1 "),
        ("1.3.6.1.4.1.2011.1", "1.3.6.1.4.1.2011.2"),
    ],
)
def test_load_oid_catalog_rejects_noncanonical_oid(tmp_path, key, stored_oid):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    _write_json(catalog, {key: _entry(stored_oid)})
    _write_json(metadata, _metadata())

    with pytest.raises(OidCatalogError, match="OID"):
        load_oid_catalog(catalog, metadata)


@pytest.mark.parametrize(
    "update_catalog, update_metadata",
    [
        (lambda entry, oid: entry.update(model=""), lambda metadata: None),
        (lambda entry, oid: entry.update(model=oid), lambda metadata: None),
        (lambda entry, oid: entry.update(FirstTypeId="AP"), lambda metadata: None),
        (lambda entry, oid: entry.update(brand="华为"), lambda metadata: None),
        (
            lambda entry, oid: entry.update(source_id="missing-source"),
            lambda metadata: None,
        ),
        (
            lambda entry, oid: None,
            lambda metadata: metadata["sources"]["huawei-product-mib"].update(official=False),
        ),
        (
            lambda entry, oid: None,
            lambda metadata: metadata["sources"]["huawei-product-mib"].update(scope="legacy-catalog"),
        ),
        (lambda entry, oid: None, lambda metadata: metadata.update(schema_version=2)),
    ],
)
def test_load_oid_catalog_rejects_invalid_catalog_boundaries(tmp_path, update_catalog, update_metadata):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    oid = "1.3.6.1.4.1.2011.2.23.968"
    entry = _entry(oid)
    metadata_data = _metadata()
    update_catalog(entry, oid)
    update_metadata(metadata_data)
    _write_json(catalog, {oid: entry})
    _write_json(metadata, metadata_data)

    with pytest.raises(OidCatalogError, match="OID_CATALOG_INVALID"):
        load_oid_catalog(catalog, metadata)


@pytest.mark.parametrize(
    "allowed_device_types",
    [
        ["switch", "router", "firewall", "loadbalance", "ap"],
        ["switch", "firewall", "loadbalance"],
        ["switch", ["router"], "firewall", "loadbalance"],
        ["switch", {"router": "router"}, "firewall", "loadbalance"],
    ],
    ids=[
        "rejects-extra-device-type",
        "rejects-missing-device-type",
        "rejects-array-device-type",
        "rejects-object-device-type",
    ],
)
def test_load_oid_catalog_requires_exact_allowed_device_types(tmp_path, allowed_device_types):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    oid = "1.3.6.1.4.1.2011.2.23.968"
    metadata_data = _metadata()
    metadata_data["allowed_device_types"] = allowed_device_types
    _write_json(catalog, {oid: _entry(oid)})
    _write_json(metadata, metadata_data)

    with pytest.raises(OidCatalogError, match="OID_CATALOG_INVALID"):
        load_oid_catalog(catalog, metadata)


def test_load_oid_catalog_rejects_duplicate_oid_json_key(tmp_path):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    oid = "1.3.6.1.4.1.2011.2.23.968"
    entry = json.dumps(_entry(oid), ensure_ascii=False)
    catalog.write_text(f'{{"{oid}": {entry}, "{oid}": {entry}}}', encoding="utf-8")
    _write_json(metadata, _metadata())

    with pytest.raises(OidCatalogError, match="OID_CATALOG_INVALID"):
        load_oid_catalog(catalog, metadata)


def test_load_oid_catalog_rejects_duplicate_source_id_json_key(tmp_path):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    oid = "1.3.6.1.4.1.2011.2.23.968"
    metadata_data = _metadata()
    source = json.dumps(metadata_data["sources"]["huawei-product-mib"], ensure_ascii=False)
    metadata_without_sources = {key: value for key, value in metadata_data.items() if key != "sources"}
    metadata.write_text(
        json.dumps(metadata_without_sources, ensure_ascii=False)[:-1]
        + f', "sources": {{"huawei-product-mib": {source}, '
        + f'"huawei-product-mib": {source}}}}}',
        encoding="utf-8",
    )
    _write_json(catalog, {oid: _entry(oid)})

    with pytest.raises(OidCatalogError, match="OID_CATALOG_INVALID"):
        load_oid_catalog(catalog, metadata)


def test_load_oid_catalog_rejects_legacy_source_missing_audit_fields(tmp_path):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    oid = "1.3.6.1.4.1.2011.2.23.968"
    entry = _entry(oid)
    entry.update(source_id="legacy-catalog-v1", verification="legacy-compatible")
    metadata_data = _metadata()
    metadata_data["sources"]["legacy-catalog-v1"] = {
        "vendor": "Multiple",
        "official": False,
        "scope": "legacy-catalog",
    }
    _write_json(catalog, {oid: entry})
    _write_json(metadata, metadata_data)

    with pytest.raises(OidCatalogError, match="OID_CATALOG_INVALID"):
        load_oid_catalog(catalog, metadata)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("vendor", ""),
        ("document", []),
        ("version", None),
        ("verified_at", "   "),
        ("verified_at", "2026-02-30"),
        ("verified_at", "22-07-2026"),
        ("scope", 1),
        ("official", 1),
        ("url", []),
        ("url", ""),
        ("url", "ftp://vendor.example/mib"),
    ],
    ids=[
        "blank-vendor",
        "non-string-document",
        "non-string-version",
        "blank-verified-at",
        "invalid-calendar-date",
        "non-iso-date",
        "non-string-scope",
        "non-boolean-official",
        "non-string-url",
        "blank-verified-url",
        "non-http-verified-url",
    ],
)
def test_load_oid_catalog_rejects_malformed_source_audit_values(tmp_path, field, value):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    oid = "1.3.6.1.4.1.2011.2.23.968"
    metadata_data = _metadata()
    metadata_data["sources"]["huawei-product-mib"][field] = value
    _write_json(catalog, {oid: _entry(oid)})
    _write_json(metadata, metadata_data)

    with pytest.raises(OidCatalogError, match="OID_CATALOG_INVALID"):
        load_oid_catalog(catalog, metadata)


def test_load_oid_catalog_allows_empty_url_for_audited_legacy_source(tmp_path):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    oid = "1.3.6.1.4.1.2011.2.23.968"
    entry = _entry(oid)
    entry.update(source_id="legacy-catalog-v1", verification="legacy-compatible")
    metadata_data = _metadata()
    metadata_data["sources"]["legacy-catalog-v1"] = {
        "vendor": "Multiple",
        "url": "",
        "document": "BK-Lite legacy systemoid.json",
        "version": "pre-2026",
        "verified_at": "2026-07-22",
        "official": False,
        "scope": "legacy-catalog",
    }
    _write_json(catalog, {oid: entry})
    _write_json(metadata, metadata_data)

    assert load_oid_catalog(catalog, metadata)[oid].verification == "legacy-compatible"


@pytest.mark.parametrize(
    "case",
    [
        "both-missing",
        "gaps-missing",
        "details-missing",
        "gaps-not-object",
        "details-not-object",
        "missing-detail",
        "orphan-detail",
        "invalid-device-type",
        "mismatched-device-types",
        "blank-reason",
        "non-http-url",
        "blank-verified-at",
        "invalid-verified-at",
        "malformed-related-urls",
    ],
)
def test_load_oid_catalog_rejects_malformed_coverage_gap_metadata(tmp_path, case):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    oid = "1.3.6.1.4.1.2011.2.23.968"
    metadata_data = _metadata()
    metadata_data["coverage_gaps"] = {"Huawei": ["switch"]}
    metadata_data["coverage_gap_details"] = {
        "Huawei": {
            "device_types": ["switch"],
            "reason": "官方入口未提供产品级 sysObjectID。",
            "url": "https://support.huawei.example/",
            "verified_at": "2026-07-22",
        }
    }
    if case == "both-missing":
        metadata_data.pop("coverage_gaps")
        metadata_data.pop("coverage_gap_details")
    elif case == "gaps-missing":
        metadata_data.pop("coverage_gaps")
    elif case == "details-missing":
        metadata_data.pop("coverage_gap_details")
    elif case == "gaps-not-object":
        metadata_data["coverage_gaps"] = []
    elif case == "details-not-object":
        metadata_data["coverage_gap_details"] = []
    elif case == "missing-detail":
        metadata_data["coverage_gap_details"] = {}
    elif case == "orphan-detail":
        metadata_data["coverage_gaps"] = {}
    elif case == "invalid-device-type":
        metadata_data["coverage_gaps"]["Huawei"] = ["ap"]
        metadata_data["coverage_gap_details"]["Huawei"]["device_types"] = ["ap"]
    elif case == "mismatched-device-types":
        metadata_data["coverage_gap_details"]["Huawei"]["device_types"] = ["router"]
    elif case == "blank-reason":
        metadata_data["coverage_gap_details"]["Huawei"]["reason"] = " "
    elif case == "non-http-url":
        metadata_data["coverage_gap_details"]["Huawei"]["url"] = "support portal"
    elif case == "blank-verified-at":
        metadata_data["coverage_gap_details"]["Huawei"]["verified_at"] = ""
    elif case == "invalid-verified-at":
        metadata_data["coverage_gap_details"]["Huawei"]["verified_at"] = "2026-02-30"
    else:
        metadata_data["coverage_gap_details"]["Huawei"]["related_urls"] = [1]
    _write_json(catalog, {oid: _entry(oid)})
    _write_json(metadata, metadata_data)

    with pytest.raises(OidCatalogError, match="OID_CATALOG_INVALID"):
        load_oid_catalog(catalog, metadata)


def test_load_oid_catalog_rejects_verified_type_also_declared_as_coverage_gap(
    tmp_path,
):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    oid = "1.3.6.1.4.1.2011.2.23.968"
    metadata_data = _metadata()
    metadata_data["coverage_gaps"] = {"Huawei": ["switch"]}
    metadata_data["coverage_gap_details"] = {
        "Huawei": {
            "device_types": ["switch"],
            "reason": "官方入口未提供其他产品级 sysObjectID。",
            "url": "https://support.huawei.example/",
            "verified_at": "2026-07-22",
        }
    }
    _write_json(catalog, {oid: _entry(oid)})
    _write_json(metadata, metadata_data)

    with pytest.raises(OidCatalogError, match="OID_CATALOG_INVALID"):
        load_oid_catalog(catalog, metadata)


def test_load_oid_catalog_allows_legacy_type_declared_as_coverage_gap(tmp_path):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    oid = "1.3.6.1.4.1.2011.2.23.968"
    entry = _entry(oid)
    entry.update(source_id="legacy-catalog-v1", verification="legacy-compatible")
    metadata_data = _metadata()
    metadata_data["sources"]["legacy-catalog-v1"] = {
        "vendor": "Multiple",
        "url": "",
        "document": "BK-Lite legacy systemoid.json",
        "version": "pre-2026",
        "verified_at": "2026-07-22",
        "official": False,
        "scope": "legacy-catalog",
    }
    metadata_data["coverage_gaps"] = {"Huawei": ["switch"]}
    metadata_data["coverage_gap_details"] = {
        "Huawei": {
            "device_types": ["switch"],
            "reason": "历史兼容记录没有官方产品级 sysObjectID 证据。",
            "url": "https://support.huawei.example/",
            "verified_at": "2026-07-22",
        }
    }
    _write_json(catalog, {oid: entry})
    _write_json(metadata, metadata_data)

    assert load_oid_catalog(catalog, metadata)[oid].verification == "legacy-compatible"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("catalog_version", 20260722),
        ("catalog_version", "   "),
    ],
    ids=[
        "rejects-boolean-schema-version",
        "rejects-number-catalog-version",
        "rejects-blank-catalog-version",
    ],
)
def test_load_oid_catalog_rejects_malformed_metadata_versions(tmp_path, field, value):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    oid = "1.3.6.1.4.1.2011.2.23.968"
    metadata_data = _metadata()
    metadata_data[field] = value
    _write_json(catalog, {oid: _entry(oid)})
    _write_json(metadata, metadata_data)

    with pytest.raises(OidCatalogError, match="OID_CATALOG_INVALID"):
        load_oid_catalog(catalog, metadata)


@pytest.mark.parametrize("brand", ["华为 ", " 华为"])
def test_load_oid_catalog_rejects_whitespace_padded_brand_alias(tmp_path, brand):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    oid = "1.3.6.1.4.1.2011.2.23.968"
    entry = _entry(oid)
    entry["brand"] = brand
    _write_json(catalog, {oid: entry})
    _write_json(metadata, _metadata())

    with pytest.raises(OidCatalogError, match="OID_CATALOG_INVALID"):
        load_oid_catalog(catalog, metadata)


def test_production_catalog_is_valid_and_preserves_exact_legacy_oid_set():
    raw = json.loads(SYSTEMOID_PATH.read_text(encoding="utf-8"))

    entries = load_oid_catalog(SYSTEMOID_PATH, SYSTEMOID_METADATA_PATH)
    legacy_raw = {oid: entry for oid, entry in raw.items() if entry["verification"] == "legacy-compatible"}
    ordered_oids = sorted(legacy_raw, key=lambda oid: tuple(int(part) for part in oid.split(".")))
    oid_sequence_digest = hashlib.sha256("\n".join(ordered_oids).encode("ascii")).hexdigest()
    legacy_content_digest = hashlib.sha256(
        json.dumps(
            legacy_raw,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    foreign_counts = Counter(entry["brand"] for entry in raw.values() if entry["brand"] in FOREIGN_CATALOG_BRAND_COUNTS)

    assert len(legacy_raw) == 1998, "信创目录的 legacy-compatible 条目数已变化"
    assert oid_sequence_digest == "4fdc993a31ac2742508c14e7bb756700993a2066b11dbb355c55dc23dc9314e2", "历史 SOID 数值排序序列已变化（ASCII 编码、LF 分隔、无末尾换行）"
    assert legacy_content_digest == ("8857e4af97adce57402e08966c056bd6e5cb78fbed760e0d2a0921e5e69a9138"), "legacy-compatible SOID 的字段语义已变化"
    assert foreign_counts == FOREIGN_CATALOG_BRAND_COUNTS, "国际厂商目录条目不得增加"
    assert "1.3.6.1.4.1.8072.3.2.10" not in raw
    assert len(entries) == len(raw)
    assert len(raw) > 1998, "verified 与信创前缀必须在历史目录之外新增"
    assert "1.3.6.1.4.1.9.1.1208" in entries
    assert "1.3.6.1.4.1.2011.2.23.968" in entries
    assert "1.3.6.1.4.1.25506.1.2609" in entries
    assert entries["1.3.6.1.4.1.8886"].brand == "Raisecom"
    assert entries["1.3.6.1.4.1.47646"].brand == "Qi-Anxin"
    assert entries["1.3.6.1.4.1.3807"].brand == "FiberHome"
    assert entries["1.3.6.1.4.1.32328"].brand == "LegendSec"


def test_domestic_catalog_covers_or_declares_required_families():
    entries = load_oid_catalog(SYSTEMOID_PATH, SYSTEMOID_METADATA_PATH)
    metadata = json.loads(SYSTEMOID_METADATA_PATH.read_text(encoding="utf-8"))
    actual = {}
    for entry in entries.values():
        if entry.verification == "verified":
            actual.setdefault(entry.brand, set()).add(entry.device_type)
    gaps = {brand: set(device_types) for brand, device_types in metadata.get("coverage_gaps", {}).items()}

    for brand, device_types in DOMESTIC_REQUIRED_FAMILIES.items():
        verified_types = actual.get(brand, set())
        gap_types = gaps.get(brand, set())
        assert verified_types.isdisjoint(gap_types), f"{brand} 已 verified 类型仍被声明为缺口: " f"{sorted(verified_types & gap_types)}"
        missing = device_types - verified_types - gap_types
        assert not missing, f"{brand} 缺少 verified 数据或显式缺口: {sorted(missing)}"


def test_domestic_coverage_gaps_have_matching_official_audit_details():
    metadata = json.loads(SYSTEMOID_METADATA_PATH.read_text(encoding="utf-8"))
    gaps = metadata.get("coverage_gaps", {})
    details = metadata.get("coverage_gap_details", {})

    assert gaps
    assert set(details) == set(gaps)
    for brand, device_types in gaps.items():
        detail = details[brand]
        assert device_types
        assert set(detail["device_types"]) == set(device_types)
        assert detail["reason"].strip()
        assert detail["url"].startswith("https://")
        assert "checked_at" not in detail
        assert detail["verified_at"] in {"2026-07-22", "2026-08-28"}


def test_domestic_verified_entries_use_exact_official_product_identity_sources():
    entries = load_oid_catalog(SYSTEMOID_PATH, SYSTEMOID_METADATA_PATH)
    verified_oids = {
        oid
        for oid, entry in entries.items()
        if entry.verification == "verified" and entry.brand in DOMESTIC_REQUIRED_FAMILIES and entry.source_id in DOMESTIC_TASK_SOURCE_IDS
    }

    assert verified_oids == set(DOMESTIC_VERIFIED_OIDS)

    for oid, (brand, model, device_type) in DOMESTIC_VERIFIED_OIDS.items():
        entry = entries[oid]
        assert (entry.brand, entry.model, entry.device_type) == (
            brand,
            model,
            device_type,
        )
        assert entry.verification == "verified"


def test_international_catalog_covers_or_declares_required_families():
    entries = load_oid_catalog(SYSTEMOID_PATH, SYSTEMOID_METADATA_PATH)
    metadata = json.loads(SYSTEMOID_METADATA_PATH.read_text(encoding="utf-8"))
    actual = {}
    for entry in entries.values():
        if entry.verification == "verified":
            actual.setdefault(entry.brand, set()).add(entry.device_type)
    gaps = {brand: set(device_types) for brand, device_types in metadata.get("coverage_gaps", {}).items()}

    for brand, device_types in INTERNATIONAL_REQUIRED_FAMILIES.items():
        verified_types = actual.get(brand, set())
        gap_types = gaps.get(brand, set())
        assert verified_types.isdisjoint(gap_types), f"{brand} 已 verified 类型仍被声明为缺口: " f"{sorted(verified_types & gap_types)}"
        missing = device_types - verified_types - gap_types
        assert not missing, f"{brand} 缺少 verified 数据或显式缺口: {sorted(missing)}"


def test_international_coverage_gaps_have_matching_official_audit_details():
    metadata = json.loads(SYSTEMOID_METADATA_PATH.read_text(encoding="utf-8"))
    gaps = metadata.get("coverage_gaps", {})
    details = metadata.get("coverage_gap_details", {})

    for brand in INTERNATIONAL_REQUIRED_FAMILIES:
        if brand not in gaps:
            continue
        detail = details[brand]
        assert gaps[brand]
        assert set(detail["device_types"]) == set(gaps[brand])
        assert detail["reason"].strip()
        assert detail["url"].startswith("https://")
        assert "checked_at" not in detail
        assert detail["verified_at"] in {"2026-07-22", "2026-08-28"}


def test_international_verified_entries_use_exact_official_product_identity_sources():
    entries = load_oid_catalog(SYSTEMOID_PATH, SYSTEMOID_METADATA_PATH)
    verified_oids = {
        oid
        for oid, entry in entries.items()
        if entry.verification == "verified" and entry.brand in INTERNATIONAL_REQUIRED_FAMILIES and entry.source_id in INTERNATIONAL_TASK_SOURCE_IDS
    }

    assert verified_oids == set(INTERNATIONAL_VERIFIED_OIDS)

    for oid, (brand, model, device_type) in INTERNATIONAL_VERIFIED_OIDS.items():
        entry = entries[oid]
        assert (entry.brand, entry.model, entry.device_type) == (
            brand,
            model,
            device_type,
        )
        assert entry.source_id in INTERNATIONAL_TASK_SOURCE_IDS
        assert entry.verification == "verified"


def test_all_verified_entries_use_auditable_official_product_identity_sources():
    entries = load_oid_catalog(SYSTEMOID_PATH, SYSTEMOID_METADATA_PATH)
    metadata = json.loads(SYSTEMOID_METADATA_PATH.read_text(encoding="utf-8"))

    for entry in entries.values():
        if entry.verification != "verified":
            continue
        source = metadata["sources"][entry.source_id]
        assert source["vendor"] == entry.brand
        assert source["official"] is True
        assert source["scope"] == "product-identity"
        assert source["url"].startswith("https://")
        assert source["document"].strip()
        assert source["version"].strip()
        assert source["verified_at"] in {"2026-07-22", "2026-08-28"}


def test_production_catalog_contains_no_noncanonical_brand_aliases():
    raw = json.loads(SYSTEMOID_PATH.read_text(encoding="utf-8"))
    metadata = json.loads(SYSTEMOID_METADATA_PATH.read_text(encoding="utf-8"))

    for brand_alias in metadata["brand_aliases"]:
        assert all(entry["brand"] != brand_alias for entry in raw.values()), brand_alias


def test_production_catalog_locks_legacy_entry_shapes():
    raw = json.loads(SYSTEMOID_PATH.read_text(encoding="utf-8"))
    metadata = json.loads(SYSTEMOID_METADATA_PATH.read_text(encoding="utf-8"))

    assert all(oid == entry["OID"] for oid, entry in raw.items())
    assert all(entry["verification"] != "verified" or entry["model"] != oid for oid, entry in raw.items())
    assert all(
        entry["verification"] == "legacy-compatible" or metadata["sources"][entry["source_id"]]["scope"] == "product-identity"
        for oid, entry in raw.items()
        if oid.endswith(".0")
    )
    assert {entry["FirstTypeId"].lower() for entry in raw.values()} == {
        "switch",
        "router",
        "firewall",
        "loadbalance",
    }


def test_production_catalog_version_and_xinchuang_prefix_rows():
    raw = json.loads(SYSTEMOID_PATH.read_text(encoding="utf-8"))
    metadata = json.loads(SYSTEMOID_METADATA_PATH.read_text(encoding="utf-8"))
    entries = load_oid_catalog(SYSTEMOID_PATH, SYSTEMOID_METADATA_PATH)

    assert metadata["catalog_version"] == "2026.08.28"
    assert all(len(oid) <= 64 for oid in raw)
    assert "Hillstone" not in metadata["coverage_gaps"]
    assert metadata["coverage_gaps"]["H3C"] == ["firewall"]
    assert "switch" not in metadata["coverage_gaps"]["H3C"]
    for brand in ("NSFOCUS", "Qi-Anxin"):
        assert metadata["coverage_gap_details"][brand]["reason"] == "已用 IANA 企业前缀识别厂商，官网仍无产品级 sysObjectID"
    assert entries["1.3.6.1.4.1.61878"].brand == "H3C"
    assert all(not oid.startswith("1.3.6.1.4.1.61878.") for oid in raw)
    assert entries["1.3.6.1.4.1.32328"].brand == "LegendSec"
    assert entries["1.3.6.1.4.1.47646"].brand == "Qi-Anxin"
    assert raw["1.3.6.1.4.1.8886"]["model"] == "未知"
    assert raw["1.3.6.1.4.1.8886"]["verification"] == "legacy-compatible"
    assert raw["1.3.6.1.4.1.28557.1.12"]["FirstTypeId"] == "Switch"
    assert "1.3.6.1.4.1.28557.1.70" not in raw
    assert "1.3.6.1.4.1.25506.1.772" in raw
    assert raw["1.3.6.1.4.1.25506.1.772"]["verification"] == "legacy-compatible"
