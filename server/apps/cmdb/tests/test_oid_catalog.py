import json

import pytest

from apps.cmdb.services.oid_catalog import OidCatalogError, load_oid_catalog


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
