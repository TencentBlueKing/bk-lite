import json
import re
from dataclasses import dataclass
from pathlib import Path


SUPPORT_FILES = Path(__file__).resolve().parents[1] / "support-files"
SYSTEMOID_PATH = SUPPORT_FILES / "systemoid.json"
SYSTEMOID_METADATA_PATH = SUPPORT_FILES / "systemoid.meta.json"
OID_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))+$")
VERIFICATION_STATES = {"verified", "legacy-compatible"}
ALLOWED_DEVICE_TYPES = {"switch", "router", "firewall", "loadbalance"}
REQUIRED_SOURCE_FIELDS = {
    "vendor",
    "url",
    "document",
    "version",
    "verified_at",
    "official",
    "scope",
}


class OidCatalogError(ValueError):
    pass


@dataclass(frozen=True)
class OidCatalogEntry:
    oid: str
    model: str
    brand: str
    device_type: str
    source_id: str
    verification: str


@dataclass(frozen=True)
class OidSyncResult:
    created: int
    updated: int
    unchanged: int
    custom_override_oids: tuple[str, ...]
    stale_builtin_oids: tuple[str, ...]


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise OidCatalogError(f"OID_CATALOG_INVALID: duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_json(path: Path):
    try:
        return json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise OidCatalogError(f"OID_CATALOG_INVALID: {path.name}") from exc


def load_oid_catalog(
    catalog_path: Path = SYSTEMOID_PATH,
    metadata_path: Path = SYSTEMOID_METADATA_PATH,
) -> dict[str, OidCatalogEntry]:
    raw_catalog = _read_json(Path(catalog_path))
    metadata = _read_json(Path(metadata_path))
    if not isinstance(metadata, dict):
        raise OidCatalogError("OID_CATALOG_INVALID: metadata")

    allowed_types = metadata.get("allowed_device_types")
    aliases = metadata.get("brand_aliases", {})
    sources = metadata.get("sources", {})
    entries: dict[str, OidCatalogEntry] = {}

    if metadata.get("schema_version") != 1 or not metadata.get("catalog_version"):
        raise OidCatalogError("OID_CATALOG_INVALID: metadata version")
    if not isinstance(raw_catalog, dict) or not raw_catalog:
        raise OidCatalogError("OID_CATALOG_INVALID: catalog must be a non-empty object")
    if not isinstance(aliases, dict) or not isinstance(sources, dict):
        raise OidCatalogError("OID_CATALOG_INVALID: metadata structure")
    if (
        not isinstance(allowed_types, list)
        or len(allowed_types) != len(ALLOWED_DEVICE_TYPES)
        or any(not isinstance(device_type, str) for device_type in allowed_types)
        or set(allowed_types) != ALLOWED_DEVICE_TYPES
    ):
        raise OidCatalogError("OID_CATALOG_INVALID: allowed device types")
    for source_id, source in sources.items():
        if not isinstance(source, dict) or not REQUIRED_SOURCE_FIELDS.issubset(source):
            raise OidCatalogError(f"OID_CATALOG_INVALID: source audit fields {source_id}")

    for key, raw in raw_catalog.items():
        oid = raw.get("OID") if isinstance(raw, dict) else None
        if key != oid or not isinstance(oid, str) or not OID_PATTERN.fullmatch(oid):
            raise OidCatalogError(f"OID_CATALOG_INVALID: OID {key!r}")

        required = {
            "FirstTypeId",
            "FirstTypeName",
            "SecondTypeId",
            "SecondTypeName",
            "model",
            "brand",
            "source_id",
            "verification",
        }
        if any(
            not isinstance(raw.get(field), str) or not raw[field].strip()
            for field in required
        ):
            raise OidCatalogError(f"OID_CATALOG_INVALID: required fields for {oid}")

        device_type = raw["FirstTypeId"].lower()
        if device_type not in ALLOWED_DEVICE_TYPES:
            raise OidCatalogError(f"OID_CATALOG_INVALID: device type for {oid}")
        if raw["brand"] in aliases:
            raise OidCatalogError(f"OID_CATALOG_INVALID: noncanonical brand for {oid}")

        source_id = raw["source_id"]
        verification = raw["verification"]
        if source_id not in sources or verification not in VERIFICATION_STATES:
            raise OidCatalogError(f"OID_CATALOG_INVALID: source for {oid}")
        if verification == "verified":
            source = sources[source_id]
            if (
                source["official"] is not True
                or source["scope"] != "product-identity"
            ):
                raise OidCatalogError(f"OID_CATALOG_INVALID: verified source for {oid}")
            if raw["model"].strip() == oid:
                raise OidCatalogError(f"OID_CATALOG_INVALID: verified model for {oid}")

        entries[oid] = OidCatalogEntry(
            oid=oid,
            model=raw["model"].strip(),
            brand=raw["brand"].strip(),
            device_type=device_type,
            source_id=source_id,
            verification=verification,
        )
    return entries
