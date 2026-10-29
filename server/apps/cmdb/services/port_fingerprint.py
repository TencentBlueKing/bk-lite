from apps.cmdb.models.collect_model import PortFingerprint
from apps.core.logger import cmdb_logger as logger

# 可网段主机发现的配置采集对象监听口；不含 SSH/IPMI/云 API 管理口。
BUILTIN_PORT_FINGERPRINTS = (
    (3306, "mysql"),
    (5432, "postgresql"),
    (1433, "mssql"),
    (1521, "oracle"),
    (8086, "influxdb"),
    (6379, "redis"),
    (27017, "mongodb"),
    (9200, "es"),
    (80, "nginx"),
    (443, "nginx"),
    (80, "apache"),
    (80, "openresty"),
    (443, "openresty"),
    (8080, "tomcat"),
    (9092, "kafka"),
    (2181, "zookeeper"),
    (5672, "rabbitmq"),
    (15672, "rabbitmq"),
    (8500, "consul"),
    (2379, "etcd"),
    (11211, "memcached"),
    (9000, "minio"),
    (80, "haproxy"),
    (80, "iis"),
    (61616, "activemq"),
    (9876, "rocketmq"),
    (3128, "squid"),
    (8848, "nacos"),
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
                    enabled=True,
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
    if not model_id:
        return []
    return list(
        PortFingerprint.objects.filter(target_type=model_id, protocol=PortFingerprint.PROTOCOL_TCP, enabled=True)
        .order_by("port")
        .values_list("port", flat=True)
    )


def enabled_port_fingerprints() -> list[dict]:
    rows = PortFingerprint.objects.filter(protocol=PortFingerprint.PROTOCOL_TCP, enabled=True).order_by("port", "target_type")
    return [{"port": int(row.port), "target_type": row.target_type, "protocol": row.protocol} for row in rows]


def scan_database_ports_by_type() -> dict[str, list[int]]:
    return {model_id: ports_for_scan_type(model_id) for model_id in ("mysql", "postgresql", "mssql")}
