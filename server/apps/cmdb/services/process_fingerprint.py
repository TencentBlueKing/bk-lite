import re

from apps.cmdb.models.collect_model import ProcessFingerprint
from apps.cmdb.services.port_fingerprint import BUILTIN_PORT_FINGERPRINTS
from apps.core.logger import cmdb_logger as logger

FINGERPRINT_TARGET_TYPES = frozenset(target_type for _, target_type in BUILTIN_PORT_FINGERPRINTS)

# (target_type, linux_process, windows_image)
BUILTIN_PROCESS_FINGERPRINTS = (
    ("mysql", r"mysqld|mariadbd", "mysqld.exe"),
    ("postgresql", r"(^|[/\s])postgres([/\s]|$)", "postgres.exe"),
    ("mssql", r"sqlservr", "sqlservr.exe"),
    ("oracle", r"tnslsnr|ora_pmon", "oracle.exe"),
    ("influxdb", r"influxd", "influxd.exe"),
    ("redis", r"redis-server", "redis-server.exe"),
    ("mongodb", r"mongod", "mongod.exe"),
    ("es", r"org\.elasticsearch\.bootstrap\.Elasticsearch|[/\s]elasticsearch([/\s]|$)", ""),
    ("nginx", r"(^|[/\s])nginx([/\s]|$)", "nginx.exe"),
    ("apache", r"httpd|apache2", "httpd.exe"),
    ("openresty", r"openresty", ""),
    ("tomcat", r"org\.apache\.catalina\.startup\.(Bootstrap|Tomcat)", ""),
    ("kafka", r"kafka\.Kafka", ""),
    ("zookeeper", r"org\.apache\.zookeeper\.server", ""),
    ("rabbitmq", r"rabbitmq", ""),
    ("consul", r"(^|[/\s])consul([/\s]|$)", "consul.exe"),
    ("etcd", r"(^|[/\s])etcd([/\s]|$)", "etcd.exe"),
    ("memcached", r"memcached", "memcached.exe"),
    ("minio", r"(^|[/\s])minio([/\s]|$)", "minio.exe"),
    ("haproxy", r"haproxy", "haproxy.exe"),
    ("iis", "", "w3wp.exe"),
    ("activemq", r"org\.apache\.activemq", ""),
    ("rocketmq", r"org\.apache\.rocketmq", ""),
    ("squid", r"squid", "squid.exe"),
    ("nacos", r"nacos", ""),
)


def linux_process_matches(pattern: str, command_line: str) -> bool:
    text = str(command_line or "")
    expr = str(pattern or "").strip()
    if not expr or not text:
        return False
    try:
        return re.search(expr, text) is not None
    except re.error:
        return False


def sync_builtin_process_fingerprints(*, dry_run=False):
    created = 0
    unchanged = 0
    skipped_user = 0
    for target_type, linux_process, windows_image in BUILTIN_PROCESS_FINGERPRINTS:
        existing = ProcessFingerprint.objects.filter(
            target_type=target_type,
            linux_process=linux_process,
            windows_image=windows_image,
        ).first()
        if existing is None:
            if not dry_run:
                ProcessFingerprint.objects.create(
                    target_type=target_type,
                    linux_process=linux_process,
                    windows_image=windows_image,
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
        "event=process_fingerprint_sync created=%s unchanged=%s skipped_user=%s dry_run=%s",
        created,
        unchanged,
        skipped_user,
        dry_run,
    )
    return {"created": created, "unchanged": unchanged, "skipped_user": skipped_user}


def enabled_process_fingerprints() -> list[dict]:
    rows = ProcessFingerprint.objects.filter(enabled=True).order_by("target_type", "id")
    return [
        {
            "target_type": row.target_type,
            "linux_process": row.linux_process,
            "windows_image": row.windows_image,
        }
        for row in rows
    ]
