from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone as django_timezone

from apps.core.logger import log_logger as logger
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.time_util import parse_rfc3339_utc
from apps.log.constants.victoriametrics import VictoriaLogsConstants
from apps.log.models.syslog_source_device import SYSLOG_SOURCE_DEVICE_ACTIVE_WINDOW, SYSLOG_SOURCE_DEVICE_DISCOVER_WINDOW, SyslogSourceDevice
from apps.log.utils.query_log import VictoriaMetricsAPI
from apps.node_mgmt.constants.language import LanguageConstants
from apps.node_mgmt.models.cloud_region import CloudRegion

DISCOVER_STARTED = "event=syslog_source_device_discover_started"
DISCOVER_FINISHED = "event=syslog_source_device_discover_finished region_count=%s written_rows=%s truncated_regions=%s"
DISCOVER_TRUNCATED = "event=syslog_source_device_query_truncated truncated=true cloud_region_id=%s row_count=%s"
DISCOVER_SKIPPED = "event=syslog_source_device_rows_skipped skipped=%s"
DISCOVER_FAILED = "event=syslog_source_device_discover_failed cloud_region_id=%s failed_stage=%s error_type=%s"
_SAFE_FAILURE_MESSAGE = "syslog source device discovery failed"
_NUMERIC_TIME = re.compile(r"-?\d+(?:\.\d+)?")
_FRACTION = re.compile(r"(\.\d+)(?=(?:Z|[+-]\d{2}:\d{2})$)")

PAGE_SIZE_MAX = 100


def quote_logsql_value(value) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def build_syslog_stats_query(cloud_region_id: str) -> str:
    return (
        f'collect_type:"syslog" AND cloud_region_id:{quote_logsql_value(cloud_region_id)} '
        "| stats by (cloud_region_id, source_ip, hostname) min(_time) as first_seen, max(_time) as last_seen"
    )


def build_syslog_source_device_search_query(cloud_region_id: str, source_ip: str, hostname: str) -> str:
    return (
        'collect_type:"syslog" AND '
        f"cloud_region_id:{quote_logsql_value(cloud_region_id)} AND "
        f"source_ip:{quote_logsql_value(source_ip)} AND "
        f"hostname:{quote_logsql_value(hostname)}"
    )


def syslog_source_device_status(last_seen: datetime, now: datetime) -> str:
    if last_seen >= now - SYSLOG_SOURCE_DEVICE_ACTIVE_WINDOW:
        return "active"
    return "silent"


def discover_syslog_source_devices(*, now=None) -> dict:
    now = now or django_timezone.now()
    logger.info(DISCOVER_STARTED)
    regions = list(CloudRegion.objects.order_by("id").values_list("id", flat=True))
    written_rows = 0
    truncated_regions = 0
    skipped_rows = 0
    try:
        api = VictoriaMetricsAPI()
    except Exception as exc:
        _log_discover_failure(exc, failed_stage="query", cloud_region_id="")
        return _discover_result(len(regions), written_rows, truncated_regions, failed=True)

    window_end = int(now.timestamp())
    window_start = int((now - SYSLOG_SOURCE_DEVICE_DISCOVER_WINDOW).timestamp())
    limit = VictoriaLogsConstants.QUERY_LIMIT_MAX
    for region_id in regions:
        cloud_region_id = str(region_id)
        try:
            rows = api.query(
                build_syslog_stats_query(cloud_region_id),
                window_start,
                window_end,
                limit,
            )
        except Exception as exc:
            _log_discover_failure(exc, failed_stage="query", cloud_region_id=cloud_region_id)
            return _discover_result(len(regions), written_rows, truncated_regions, failed=True)

        if not isinstance(rows, list):
            rows = []
        if len(rows) == limit:
            truncated_regions += 1
            logger.warning(DISCOVER_TRUNCATED, cloud_region_id, len(rows))

        try:
            written, skipped = _write_region_rows(rows)
        except Exception as exc:
            _log_discover_failure(exc, failed_stage="upsert", cloud_region_id=cloud_region_id)
            return _discover_result(len(regions), written_rows, truncated_regions, failed=True)
        written_rows += written
        skipped_rows += skipped

    if skipped_rows:
        logger.warning(DISCOVER_SKIPPED, skipped_rows)
    logger.info(DISCOVER_FINISHED, len(regions), written_rows, truncated_regions)
    return _discover_result(len(regions), written_rows, truncated_regions, failed=False)


def list_syslog_source_devices(
    *,
    cloud_region_id: str = "",
    source_ip: str = "",
    hostname: str = "",
    keyword: str = "",
    status: str = "",
    page: int = 1,
    page_size: int = 20,
    now=None,
    locale: str = "",
) -> dict:
    now = now or django_timezone.now()
    queryset = SyslogSourceDevice.objects.all()
    cloud_region_id = (cloud_region_id or "").strip()
    source_ip = (source_ip or "").strip()
    hostname = (hostname or "").strip()
    keyword = (keyword or "").strip()
    if cloud_region_id:
        named_ids = [str(region_id) for region_id in CloudRegion.objects.filter(name__icontains=cloud_region_id).values_list("id", flat=True)]
        queryset = queryset.filter(Q(cloud_region_id__contains=cloud_region_id) | Q(cloud_region_id__in=named_ids))
    if source_ip:
        queryset = queryset.filter(source_ip__contains=source_ip)
    if hostname:
        queryset = queryset.filter(hostname__contains=hostname)
    if keyword:
        queryset = queryset.filter(Q(source_ip__contains=keyword) | Q(hostname__contains=keyword))
    threshold = now - SYSLOG_SOURCE_DEVICE_ACTIVE_WINDOW
    if status == "active":
        queryset = queryset.filter(last_seen__gte=threshold)
    elif status == "silent":
        queryset = queryset.filter(last_seen__lt=threshold)
    queryset = queryset.order_by("-last_seen", "id")
    total = queryset.count()
    start = (page - 1) * page_size
    rows = list(queryset[start : start + page_size])
    names = _cloud_region_names([row.cloud_region_id for row in rows], locale)
    search_end = _to_millis(now)
    items = []
    for row in rows:
        items.append(
            {
                "cloud_region_id": row.cloud_region_id,
                "cloud_region_name": names.get(row.cloud_region_id, ""),
                "source_ip": row.source_ip,
                "hostname": row.hostname,
                "first_seen": row.first_seen,
                "last_seen": row.last_seen,
                "status": syslog_source_device_status(row.last_seen, now),
                "search_query": build_syslog_source_device_search_query(row.cloud_region_id, row.source_ip, row.hostname),
                "search_start": _to_millis(row.first_seen),
                "search_end": search_end,
            }
        )
    return {"count": total, "items": items}


def _discover_result(region_count: int, written_rows: int, truncated_regions: int, *, failed: bool) -> dict:
    return {
        "region_count": region_count,
        "written_rows": written_rows,
        "truncated_regions": truncated_regions,
        "failed": failed,
    }


def _log_discover_failure(exc: BaseException, *, failed_stage: str, cloud_region_id: str) -> None:
    proxy = RuntimeError(_SAFE_FAILURE_MESSAGE)
    proxy.__traceback__ = exc.__traceback__
    logger.error(
        DISCOVER_FAILED,
        cloud_region_id,
        failed_stage,
        type(exc).__name__,
        exc_info=(type(proxy), proxy, proxy.__traceback__),
    )


def _write_region_rows(rows: list) -> tuple[int, int]:
    accepted = []
    skipped = 0
    for row in rows:
        normalized = _normalize_stats_row(row)
        if normalized is None:
            skipped += 1
            continue
        accepted.append(normalized)
    merged = _merge_identities(accepted)
    with transaction.atomic():
        for identity in merged:
            _upsert_identity(identity)
    return len(merged), skipped


def _merge_identities(rows: list[dict]) -> list[dict]:
    merged: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = (row["cloud_region_id"], row["source_ip"], row["hostname"])
        current = merged.get(key)
        if current is None:
            merged[key] = row
            continue
        current["first_seen"] = min(current["first_seen"], row["first_seen"])
        current["last_seen"] = max(current["last_seen"], row["last_seen"])
    return list(merged.values())


def _upsert_identity(identity: dict) -> None:
    lookup = {
        "cloud_region_id": identity["cloud_region_id"],
        "source_ip": identity["source_ip"],
        "hostname": identity["hostname"],
    }
    with transaction.atomic():
        obj = SyslogSourceDevice.objects.select_for_update().filter(**lookup).first()
        if obj is None:
            try:
                with transaction.atomic():
                    SyslogSourceDevice.objects.create(
                        first_seen=identity["first_seen"],
                        last_seen=identity["last_seen"],
                        **lookup,
                    )
                return
            except IntegrityError:
                obj = SyslogSourceDevice.objects.select_for_update().get(**lookup)
        update_fields = []
        if identity["first_seen"] < obj.first_seen:
            obj.first_seen = identity["first_seen"]
            update_fields.append("first_seen")
        if identity["last_seen"] > obj.last_seen:
            obj.last_seen = identity["last_seen"]
            update_fields.append("last_seen")
        if update_fields:
            obj.save(update_fields=update_fields)


def _normalize_stats_row(row) -> dict | None:
    if not isinstance(row, dict):
        return None
    cloud_region_id = _required_identity(row.get("cloud_region_id"))
    source_ip = _required_identity(row.get("source_ip"))
    if cloud_region_id is None or source_ip is None:
        return None
    if len(cloud_region_id) > SyslogSourceDevice.CLOUD_REGION_ID_MAX_LENGTH or len(source_ip) > SyslogSourceDevice.SOURCE_IP_MAX_LENGTH:
        return None
    hostname = _hostname(row.get("hostname"))
    if len(hostname) > SyslogSourceDevice.HOSTNAME_MAX_LENGTH:
        return None
    try:
        first_seen = _parse_seen_time(row.get("first_seen"))
        last_seen = _parse_seen_time(row.get("last_seen"))
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    if first_seen > last_seen:
        first_seen, last_seen = last_seen, first_seen
    return {
        "cloud_region_id": cloud_region_id,
        "source_ip": source_ip,
        "hostname": hostname,
        "first_seen": first_seen,
        "last_seen": last_seen,
    }


def _required_identity(value) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        return None
    if not text:
        return None
    return text


def _hostname(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _parse_seen_time(value) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, bool) or value is None:
        raise ValueError("missing seen time")
    elif isinstance(value, (int, float)):
        parsed = _from_unix_number(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("missing seen time")
        if _NUMERIC_TIME.fullmatch(text):
            parsed = _from_unix_number(text)
        else:
            parsed = parse_rfc3339_utc(_trim_fraction(text))
    else:
        raise ValueError("unsupported seen time")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _trim_fraction(text: str) -> str:
    match = _FRACTION.search(text)
    if not match:
        return text
    digits = match.group(1)[1:]
    if len(digits) <= 6:
        return text
    return text[: match.start(1)] + "." + digits[:6] + text[match.end(1) :]


def _from_unix_number(value) -> datetime:
    if isinstance(value, str):
        number = float(value) if "." in value else int(value)
    else:
        number = value
    if isinstance(number, int):
        absolute = abs(number)
        if absolute >= 10**17:
            seconds, remainder = divmod(number, 10**9)
            micros = remainder // 1000
        elif absolute >= 10**14:
            seconds, remainder = divmod(number, 10**6)
            micros = remainder
        elif absolute >= 10**11:
            seconds, remainder = divmod(number, 10**3)
            micros = remainder * 1000
        else:
            seconds, micros = number, 0
        return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(microsecond=int(micros))
    absolute = abs(number)
    if absolute >= 10**17:
        seconds = number / 10**9
    elif absolute >= 10**14:
        seconds = number / 10**6
    elif absolute >= 10**11:
        seconds = number / 10**3
    else:
        seconds = number
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def _cloud_region_names(cloud_region_ids: list[str], locale: str = "") -> dict[str, str]:
    numeric_ids = []
    for cloud_region_id in cloud_region_ids:
        if cloud_region_id.isdigit() and len(cloud_region_id) <= 18:
            numeric_ids.append(int(cloud_region_id))
    stored_names = {}
    if numeric_ids:
        found = CloudRegion.objects.filter(id__in=numeric_ids).values_list("id", "name")
        stored_names = {str(region_id): name for region_id, name in found}
    loader = LanguageLoader(app=LanguageConstants.APP, default_lang=locale or "en")
    names = {}
    for cloud_region_id in cloud_region_ids:
        stored_name = stored_names.get(cloud_region_id, "")
        if not stored_name:
            names[cloud_region_id] = ""
            continue
        display_name = loader.get(f"{LanguageConstants.CLOUD_REGION}.{stored_name}.name")
        names[cloud_region_id] = display_name or stored_name
    return names


def _to_millis(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)
