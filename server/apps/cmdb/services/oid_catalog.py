import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.cmdb.models import OidMapping


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
_SYNC_WRITE_ATTEMPTS = 2
_OID_MAX_LENGTH = OidMapping._meta.get_field("oid").max_length
_MODEL_MAX_LENGTH = OidMapping._meta.get_field("model").max_length
_BRAND_MAX_LENGTH = OidMapping._meta.get_field("brand").max_length


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

    schema_version = metadata.get("schema_version")
    catalog_version = metadata.get("catalog_version")
    if (
        type(schema_version) is not int
        or schema_version != 1
        or not isinstance(catalog_version, str)
        or not catalog_version.strip()
    ):
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
        brand = raw["brand"].strip()
        if device_type not in ALLOWED_DEVICE_TYPES:
            raise OidCatalogError(f"OID_CATALOG_INVALID: device type for {oid}")
        if brand in aliases:
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
            brand=brand,
            device_type=device_type,
            source_id=source_id,
            verification=verification,
        )
    return entries


def sync_oid_catalog(
    entries: Mapping[str, OidCatalogEntry],
    *,
    dry_run: bool = False,
) -> OidSyncResult:
    validated_entries = _validate_sync_entries(entries)
    if dry_run:
        return _sync_oid_catalog(validated_entries, write=False)
    for attempt in range(_SYNC_WRITE_ATTEMPTS):
        try:
            with transaction.atomic():
                return _sync_oid_catalog(validated_entries, write=True)
        except IntegrityError:
            if attempt == _SYNC_WRITE_ATTEMPTS - 1:
                raise


def _validate_sync_entries(
    entries: Mapping[str, OidCatalogEntry],
) -> dict[str, OidCatalogEntry]:
    if not isinstance(entries, Mapping) or not entries:
        raise OidCatalogError("OID_CATALOG_INVALID: sync entries")

    validated_entries = {}
    for oid, entry in entries.items():
        if (
            not isinstance(oid, str)
            or not OID_PATTERN.fullmatch(oid)
            or not isinstance(entry, OidCatalogEntry)
            or entry.oid != oid
        ):
            raise OidCatalogError(f"OID_CATALOG_INVALID: sync entry {oid!r}")
        text_values = (
            entry.model,
            entry.brand,
            entry.device_type,
            entry.source_id,
            entry.verification,
        )
        if (
            any(
                not isinstance(value, str) or not value.strip()
                for value in text_values
            )
            or entry.device_type not in ALLOWED_DEVICE_TYPES
            or entry.verification not in VERIFICATION_STATES
            or len(oid) > _OID_MAX_LENGTH
            or len(entry.model) > _MODEL_MAX_LENGTH
            or len(entry.brand) > _BRAND_MAX_LENGTH
        ):
            raise OidCatalogError(f"OID_CATALOG_INVALID: sync entry {oid!r}")
        validated_entries[oid] = entry
    return validated_entries


def _sync_oid_catalog(
    entries: Mapping[str, OidCatalogEntry],
    *,
    write: bool,
) -> OidSyncResult:
    queryset = OidMapping._default_manager.all()
    if write:
        queryset = queryset.select_for_update()
    existing = {row.oid: row for row in queryset}
    to_create = []
    to_update = []
    unchanged = 0
    custom_override_oids = []
    now = timezone.now()

    for oid in sorted(entries, key=_oid_sort_key):
        entry = entries[oid]
        row = existing.get(oid)
        if row is None:
            to_create.append(
                OidMapping(
                    oid=oid,
                    model=entry.model,
                    brand=entry.brand,
                    device_type=entry.device_type,
                    built_in=True,
                )
            )
            continue
        if not row.built_in:
            custom_override_oids.append(oid)
            continue
        values = (row.model, row.brand, row.device_type)
        desired = (entry.model, entry.brand, entry.device_type)
        if values == desired:
            unchanged += 1
            continue
        row.model, row.brand, row.device_type = desired
        row.updated_at = now
        to_update.append(row)

    stale_builtin_oids = tuple(
        sorted(
            (
                oid
                for oid, row in existing.items()
                if row.built_in and oid not in entries
            ),
            key=_oid_sort_key,
        )
    )
    if write:
        OidMapping._default_manager.bulk_create(to_create, batch_size=500)
        OidMapping._default_manager.bulk_update(
            to_update,
            ["model", "brand", "device_type", "updated_at"],
            batch_size=500,
        )
    return OidSyncResult(
        created=len(to_create),
        updated=len(to_update),
        unchanged=unchanged,
        custom_override_oids=tuple(custom_override_oids),
        stale_builtin_oids=stale_builtin_oids,
    )


def _oid_sort_key(oid: str) -> tuple[int, ...]:
    return tuple(int(part) for part in oid.split("."))
