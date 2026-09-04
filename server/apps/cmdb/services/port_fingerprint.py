from apps.cmdb.models.collect_model import PortFingerprint
from apps.cmdb.models.scan_model import SCAN_DATABASE_TYPES
from apps.core.logger import cmdb_logger as logger

BUILTIN_PORT_FINGERPRINTS = (
    (3306, "mysql"),
    (5432, "postgresql"),
    (1433, "mssql"),
)


def sync_builtin_port_fingerprints(*, dry_run=False):
    created = 0
    unchanged = 0
    skipped_user = 0
    for port, target_type in BUILTIN_PORT_FINGERPRINTS:
        existing = PortFingerprint.objects.filter(port=port, target_type=target_type).first()
        if existing is None:
            if not dry_run:
                PortFingerprint.objects.create(
                    port=port,
                    protocol=PortFingerprint.PROTOCOL_TCP,
                    target_type=target_type,
                    built_in=True,
                )
            created += 1
            continue
        if not existing.built_in:
            skipped_user += 1
            continue
        unchanged += 1
    logger.info(
        "event=port_fingerprint_sync created=%s unchanged=%s skipped_user=%s dry_run=%s",
        created,
        unchanged,
        skipped_user,
        dry_run,
    )
    return {"created": created, "unchanged": unchanged, "skipped_user": skipped_user}


def ports_for_scan_type(target_type: str) -> list[int]:
    model_id = str(target_type or "").strip()
    if model_id not in SCAN_DATABASE_TYPES:
        return []
    return list(
        PortFingerprint.objects.filter(target_type=model_id, protocol=PortFingerprint.PROTOCOL_TCP).order_by("port").values_list("port", flat=True)
    )


def scan_database_ports_by_type() -> dict[str, list[int]]:
    return {model_id: ports_for_scan_type(model_id) for model_id in ("mysql", "postgresql", "mssql")}
