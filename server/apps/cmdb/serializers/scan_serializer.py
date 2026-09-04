import copy
import ipaddress

from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.cmdb.constants.constants import PERMISSION_TASK
from apps.cmdb.models.scan_model import (
    SCAN_ALLOWED_FAMILIES,
    SCAN_DATABASE_FAMILY,
    SCAN_DATABASE_TYPES,
    SCAN_IP_RANGE_MAX_SIZE,
    ScanExecution,
    ScanFamilyRun,
    ScanHit,
    ScanTask,
    merge_database_credentials,
    normalize_scan_families,
    scan_driver_type_for_model,
    scan_encrypt_model_id,
)
from apps.cmdb.services.collect_credential_contract import API_SECRET_MASK
from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.cmdb.services.encrypt_collect_password import get_collect_model_passwords
from apps.cmdb.services.scan_identity import unmatch_reason_for_hit
from apps.core.utils.serializers import AuthSerializer, UsernameSerializer


class ScanPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200

    def paginate_queryset(self, queryset, request, view=None):
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        return Response({"count": self.page.paginator.count, "items": data})


class ScanHitPagination(ScanPagination):
    page_size = 50
    max_page_size = 200


def _validate_ipv4_range(begin, end):
    try:
        begin_ip = ipaddress.IPv4Address(str(begin).strip())
        end_ip = ipaddress.IPv4Address(str(end).strip())
    except (ipaddress.AddressValueError, ValueError) as exc:
        raise serializers.ValidationError("IP 地址格式不正确") from exc
    if int(end_ip) < int(begin_ip):
        raise serializers.ValidationError("结束 IP 不能小于起始 IP")
    size = int(end_ip) - int(begin_ip) + 1
    if size > SCAN_IP_RANGE_MAX_SIZE:
        raise serializers.ValidationError("单段地址数不能超过 /21（2048）")


class ScanTaskListSerializer(AuthSerializer):
    permission_key = PERMISSION_TASK
    latest_execution = serializers.SerializerMethodField()

    class Meta:
        model = ScanTask
        fields = (
            "id",
            "name",
            "team",
            "families",
            "auto_push_monitor",
            "auto_generate_collect",
            "timeout",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "permissions",
            "latest_execution",
        )

    def get_latest_execution(self, obj):
        executions = getattr(obj, "prefetched_executions", None)
        if executions is None:
            execution = obj.executions.order_by("-id").first()
        else:
            execution = executions[0] if executions else None
        if execution is None:
            return None
        return {
            "id": execution.id,
            "status": execution.status,
            "target_count": execution.target_count,
            "received_count": execution.received_count,
        }

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["families"] = normalize_scan_families(instance.families)
        return representation


class ScanTaskSerializer(AuthSerializer):
    permission_key = PERMISSION_TASK

    class Meta:
        model = ScanTask
        fields = (
            "id",
            "name",
            "team",
            "access_point",
            "ip_ranges",
            "cloud_region",
            "families",
            "credentials",
            "auto_push_monitor",
            "auto_generate_collect",
            "timeout",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "permissions",
        )

    def validate_families(self, value):
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError("至少勾选一个凭据族")
        families = []
        for item in value:
            model_id = str(item or "").strip()
            if model_id not in SCAN_ALLOWED_FAMILIES:
                raise serializers.ValidationError(f"不支持的扫描族: {model_id}")
            if model_id not in families:
                families.append(model_id)
        return families

    def validate_ip_ranges(self, value):
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError("至少填写一个网段")
        ranges = []
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError("网段格式不正确")
            begin = str(item.get("begin") or "").strip()
            end = str(item.get("end") or "").strip()
            if not begin or not end:
                raise serializers.ValidationError("网段起止 IP 不能为空")
            _validate_ipv4_range(begin, end)
            ranges.append({"begin": begin, "end": end})
        return ranges

    def validate_access_point(self, value):
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError("请选择接入点")
        return value

    def validate_team(self, value):
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError("请选择组织")
        return value

    def _mask_credentials(self, credentials):
        masked = {}
        raw = credentials or {}
        if not isinstance(raw, dict):
            return raw
        for model_id, pool in raw.items():
            items = CollectCredentialPoolService.normalize_pool(copy.deepcopy(pool))
            encrypted_fields = get_collect_model_passwords(
                collect_model_id=scan_encrypt_model_id(model_id),
                driver_type=scan_driver_type_for_model(scan_encrypt_model_id(model_id)),
            )
            for item in items:
                if not isinstance(item, dict):
                    continue
                for field in encrypted_fields:
                    if field in item and item.get(field):
                        item[field] = API_SECRET_MASK
            masked[model_id] = items
        return masked

    def _merge_masked_credentials(self, incoming):
        incoming = merge_database_credentials(incoming)
        if self.instance is None:
            return incoming
        existing = merge_database_credentials(self.instance.decrypt_credentials or {})
        merged = {}
        for model_id, pool in (incoming or {}).items():
            old_pool = CollectCredentialPoolService.normalize_pool(existing.get(model_id) or [])
            old_by_id = {item.get("credential_id"): item for item in old_pool}
            new_pool = []
            encrypted_fields = get_collect_model_passwords(
                collect_model_id=scan_encrypt_model_id(model_id),
                driver_type=scan_driver_type_for_model(scan_encrypt_model_id(model_id)),
            )
            for item in CollectCredentialPoolService.normalize_pool(pool):
                merged_item = dict(item)
                old_item = old_by_id.get(item.get("credential_id")) or {}
                for field in encrypted_fields:
                    if merged_item.get(field) in (API_SECRET_MASK, None, ""):
                        if old_item.get(field):
                            merged_item[field] = old_item[field]
                new_pool.append(merged_item)
            merged[model_id] = new_pool
        return merged

    def validate(self, attrs):
        families = attrs.get("families")
        if families is None and self.instance is not None:
            families = self.instance.families
        families = normalize_scan_families(families or [])
        attrs["families"] = families

        cloud_region = attrs.get("cloud_region")
        if cloud_region is None and self.instance is not None:
            cloud_region = self.instance.cloud_region
        if "host" in families and not cloud_region:
            raise serializers.ValidationError({"cloud_region": "主机扫描必须填写云区域"})

        credentials = attrs.get("credentials")
        if credentials is None and self.instance is not None:
            credentials = self.instance.decrypt_credentials
        if not isinstance(credentials, dict):
            raise serializers.ValidationError({"credentials": "凭据必须按族提交"})

        credentials = merge_database_credentials(self._merge_masked_credentials(credentials))
        if self.instance is None:
            for model_id, pool in credentials.items():
                encrypted_fields = get_collect_model_passwords(
                    collect_model_id=scan_encrypt_model_id(model_id),
                    driver_type=scan_driver_type_for_model(scan_encrypt_model_id(model_id)),
                )
                for item in CollectCredentialPoolService.normalize_pool(pool):
                    for field in encrypted_fields:
                        if item.get(field) == API_SECRET_MASK:
                            raise serializers.ValidationError({"credentials": "新建任务时请重新填写凭据"})

        normalized = {}
        for model_id in families:
            pool = CollectCredentialPoolService.normalize_pool(credentials.get(model_id) or [])
            if not pool:
                raise serializers.ValidationError({"credentials": f"{model_id} 至少需要一把凭据"})
            normalized[model_id] = pool
        attrs["credentials"] = normalized
        attrs.setdefault("auto_push_monitor", False)
        attrs.setdefault("auto_generate_collect", False)
        return attrs

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        families = normalize_scan_families(instance.families)
        credentials = merge_database_credentials(instance.decrypt_credentials)
        representation["families"] = families
        representation["credentials"] = self._mask_credentials(credentials)
        return representation


class ScanFamilyRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScanFamilyRun
        fields = (
            "id",
            "model_id",
            "driver_type",
            "target_count",
            "received_count",
            "admit_status",
        )


class ScanExecutionSerializer(UsernameSerializer):
    family_runs = ScanFamilyRunSerializer(many=True, read_only=True)
    task_name = serializers.CharField(source="task.name", read_only=True)

    class Meta:
        model = ScanExecution
        fields = (
            "id",
            "task",
            "task_name",
            "status",
            "target_count",
            "received_count",
            "started_at",
            "deadline_at",
            "finished_at",
            "family_runs",
            "created_at",
            "updated_at",
        )


class ScanHitSerializer(UsernameSerializer):
    family_model_id = serializers.CharField(source="family_run.model_id", read_only=True)
    credential_label = serializers.SerializerMethodField()
    unmatch_reason = serializers.SerializerMethodField()

    class Meta:
        model = ScanHit
        fields = (
            "id",
            "execution",
            "family_run",
            "family_model_id",
            "protocol",
            "host",
            "port",
            "credential_id",
            "credential_label",
            "status",
            "soid",
            "cmdb_model_id",
            "inst_uuid",
            "attached_inst_uuid",
            "error_code",
            "unmatch_reason",
            "snapshot",
            "created_at",
            "updated_at",
        )

    def get_credential_label(self, obj):
        return _credential_label_for_hit(obj)

    def get_unmatch_reason(self, obj):
        return unmatch_reason_for_hit(obj)


def _credential_label_for_hit(hit: ScanHit) -> str:
    credential_id = str(hit.credential_id or "").strip()
    if not credential_id:
        return ""
    task = getattr(getattr(hit, "execution", None), "task", None)
    if task is None:
        return credential_id
    pool = (task.credentials or {}).get(hit.family_run.model_id) or []
    if not isinstance(pool, list):
        pool = [pool] if isinstance(pool, dict) else []
    if hit.family_run.model_id in SCAN_DATABASE_TYPES:
        extra = (task.credentials or {}).get(SCAN_DATABASE_FAMILY) or []
        if isinstance(extra, dict):
            extra = [extra]
        pool = list(pool) + list(extra)
    item = next(
        (entry for entry in pool if isinstance(entry, dict) and entry.get("credential_id") == credential_id),
        None,
    )
    if not item:
        return credential_id
    return _format_credential_label(hit.family_run.model_id, item) or credential_id


def _format_credential_label(model_id: str, item: dict) -> str:
    if model_id == "host":
        username = str(item.get("username") or "").strip() or "?"
        port = str(item.get("port") or "22").strip()
        return f"{username}@{port}"
    if model_id == "network":
        version = str(item.get("version") or "").strip() or "snmp"
        if str(item.get("community") or "").strip():
            return f"SNMP {version} · community***"
        username = str(item.get("username") or "").strip()
        if username:
            return f"SNMP {version} · {username}"
        return f"SNMP {version}"
    if model_id == "physcial_server":
        username = str(item.get("username") or "").strip() or "ipmi"
        port = str(item.get("port") or item.get("ipmi_port") or "623").strip()
        return f"{username}@{port}"
    username = str(item.get("username") or item.get("user") or "").strip()
    port = str(item.get("port") or "").strip()
    if username and port:
        return f"{username}@{port}"
    if username:
        return username
    if port:
        return f":{port}"
    return ""
