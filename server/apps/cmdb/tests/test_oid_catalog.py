import hashlib
import json

import pytest

from apps.cmdb.services.oid_catalog import (
    SYSTEMOID_METADATA_PATH,
    SYSTEMOID_PATH,
    OidCatalogError,
    load_oid_catalog,
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
}

DOMESTIC_VERIFIED_OIDS = {
    "1.3.6.1.4.1.25506.1.763": ("H3C", "MSR2630", "router"),
    "1.3.6.1.4.1.4881.250.160": ("Ruijie", "RG-WALL 160E", "firewall"),
    "1.3.6.1.4.1.4881.250.161": ("Ruijie", "RG-WALL 160S", "firewall"),
    "1.3.6.1.4.1.4881.250.1600": ("Ruijie", "RG-WALL 1600E", "firewall"),
    "1.3.6.1.4.1.4881.250.1601": ("Ruijie", "RG-WALL 1600S", "firewall"),
}

DOMESTIC_TASK_SOURCE_IDS = {
    "h3c-msr-router-rfc1213-r6749",
    "ruijie-rg-wall-vpn-snmp",
}


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _metadata():
    return {
        "schema_version": 1,
        "catalog_version": "2026.07.22",
        "allowed_device_types": ["switch", "router", "firewall", "loadbalance"],
        "brand_aliases": {"华为": "Huawei"},
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
            lambda metadata: metadata["sources"]["huawei-product-mib"].update(
                official=False
            ),
        ),
        (
            lambda entry, oid: None,
            lambda metadata: metadata["sources"]["huawei-product-mib"].update(
                scope="legacy-catalog"
            ),
        ),
        (lambda entry, oid: None, lambda metadata: metadata.update(schema_version=2)),
    ],
)
def test_load_oid_catalog_rejects_invalid_catalog_boundaries(
    tmp_path, update_catalog, update_metadata
):
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
def test_load_oid_catalog_requires_exact_allowed_device_types(
    tmp_path, allowed_device_types
):
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
    source = json.dumps(
        metadata_data["sources"]["huawei-product-mib"], ensure_ascii=False
    )
    metadata_without_sources = {
        key: value for key, value in metadata_data.items() if key != "sources"
    }
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
    legacy_raw = {
        oid: entry
        for oid, entry in raw.items()
        if entry["verification"] == "legacy-compatible"
    }
    ordered_oids = sorted(
        legacy_raw, key=lambda oid: tuple(int(part) for part in oid.split("."))
    )
    oid_sequence_digest = hashlib.sha256(
        "\n".join(ordered_oids).encode("ascii")
    ).hexdigest()
    legacy_content_digest = hashlib.sha256(
        json.dumps(
            legacy_raw,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert len(legacy_raw) == 1966, "Task 2 的 1,966 个历史 SOID 不得删改"
    assert oid_sequence_digest == "0b3de86672a357d2e64fe192f66325af8dce1bbcdd9e419072ec7570976864e3", (
        "历史 SOID 数值排序序列已变化（ASCII 编码、LF 分隔、无末尾换行）"
    )
    assert legacy_content_digest == (
        "0223b25cc4ed03c0f90c98e22983f70946d4d6d47bf4924dc483a07c6a5d3659"
    ), "Task 2 历史 SOID 的字段语义已变化"
    assert len(entries) == len(raw)
    assert len(raw) > 1966, "国内厂商 verified 条目必须在历史目录之外新增"
    assert "1.3.6.1.4.1.9.1.1208" in entries
    assert "1.3.6.1.4.1.2011.2.23.968" in entries
    assert "1.3.6.1.4.1.25506.1.2609" in entries


def test_domestic_catalog_covers_or_declares_required_families():
    entries = load_oid_catalog(SYSTEMOID_PATH, SYSTEMOID_METADATA_PATH)
    metadata = json.loads(SYSTEMOID_METADATA_PATH.read_text(encoding="utf-8"))
    actual = {}
    for entry in entries.values():
        if entry.verification == "verified":
            actual.setdefault(entry.brand, set()).add(entry.device_type)
    gaps = {
        brand: set(device_types)
        for brand, device_types in metadata.get("coverage_gaps", {}).items()
    }

    for brand, device_types in DOMESTIC_REQUIRED_FAMILIES.items():
        verified_types = actual.get(brand, set())
        gap_types = gaps.get(brand, set())
        assert verified_types.isdisjoint(gap_types), (
            f"{brand} 已 verified 类型仍被声明为缺口: "
            f"{sorted(verified_types & gap_types)}"
        )
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
        assert detail["verified_at"] == "2026-07-22"


def test_domestic_verified_entries_use_exact_official_product_identity_sources():
    entries = load_oid_catalog(SYSTEMOID_PATH, SYSTEMOID_METADATA_PATH)
    verified_oids = {
        oid
        for oid, entry in entries.items()
        if entry.verification == "verified"
        and entry.brand in DOMESTIC_REQUIRED_FAMILIES
        and entry.source_id in DOMESTIC_TASK_SOURCE_IDS
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
        assert source["verified_at"] == "2026-07-22"


@pytest.mark.parametrize(
    "brand_alias",
    [
        "华为",
        "HuaWei",
        "Hewlett-Packard",
        "Netscreen",
        "Force10",
        "NortelAlteon",
        "Venus",
    ],
)
def test_production_catalog_contains_no_noncanonical_brand_aliases(brand_alias):
    raw = json.loads(SYSTEMOID_PATH.read_text(encoding="utf-8"))

    assert all(entry["brand"] != brand_alias for entry in raw.values())


def test_production_catalog_locks_legacy_entry_shapes():
    raw = json.loads(SYSTEMOID_PATH.read_text(encoding="utf-8"))
    metadata = json.loads(SYSTEMOID_METADATA_PATH.read_text(encoding="utf-8"))

    assert all(oid == entry["OID"] for oid, entry in raw.items())
    assert all(
        entry["verification"] != "verified" or entry["model"] != oid
        for oid, entry in raw.items()
    )
    assert all(
        entry["verification"] == "legacy-compatible"
        or metadata["sources"][entry["source_id"]]["scope"] == "product-identity"
        for oid, entry in raw.items()
        if oid.endswith(".0")
    )
    assert {entry["FirstTypeId"].lower() for entry in raw.values()} == {
        "switch",
        "router",
        "firewall",
        "loadbalance",
    }
