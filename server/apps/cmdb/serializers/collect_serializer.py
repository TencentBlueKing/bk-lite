# -- coding: utf-8 --
# @File: collect_serializer.py
# @Time: 2025/3/3 13:58
# @Author: windyzhao
import copy

from rest_framework import serializers

from apps.cmdb.constants.constants import PERMISSION_TASK, CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import (
    ALLOWED_TOPOLOGY_FALLBACK_STRATEGIES,
    ALLOWED_TOPOLOGY_PROTOCOLS,
    DEFAULT_TOPOLOGY_FALLBACK_STRATEGY,
    DEFAULT_TOPOLOGY_MIN_CONFIDENCE,
    DEFAULT_TOPOLOGY_PROTOCOLS,
    CollectModels,
    OidMapping,
    normalize_topology_contract,
)
from apps.cmdb.services.collect_credential_contract import (
    API_SECRET_MASK,
    CredentialContractError,
    get_collect_credential_contract,
    validate_collect_credential,
)
from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.cmdb.services.collect_object_tree import get_collect_object_meta
from apps.cmdb.services.encrypt_collect_password import get_collect_model_passwords
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.instance_identity import normalize_inst_uuid
from apps.cmdb.services.network_config_file_policy import normalize_network_config_instance, validate_commands, validate_network_config_instance
from apps.cmdb.services.pc_collect_policy import validate_pc_collect_task
from apps.cmdb.services.winsphere_endpoint import normalize_winsphere_management_address
from apps.cmdb.utils.config_file_path import validate_absolute_path
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.core.utils.serializers import AuthSerializer, UsernameSerializer

COLLECT_RESULT_PAYLOAD_FIELDS = (
    "collect_data",
    "collect_digest",
    "format_data",
    "topology_snapshot",
)

COLLECT_MODEL_DETAIL_FIELDS = (
    "id",
    "name",
    "task_type",
    "driver_type",
    "model_id",
    "is_interval",
    "cycle_value_type",
    "cycle_value",
    "scan_cycle",
    "ip_range",
    "instances",
    "access_point",
    "credential",
    "timeout",
    "exec_status",
    "exec_time",
    "task_id",
    "params",
    "plugin_id",
    "input_method",
    "data_cleanup_strategy",
    "expire_days",
    "team",
    "is_system",
    "is_visible",
    "system_code",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
    "domain",
    "updated_by_domain",
    "permissions",
)


class CollectModelSerializer(AuthSerializer):
    STRICT_PLATFORM_TARGET_MODELS = frozenset({"sangforscp", "sangforhci"})
    TRUSTED_INSTANCE_SNAPSHOT_FIELDS = {
        "inst_uuid",
        "model_id",
        "inst_name",
        "ip_addr",
        "ip",
        "host",
        "name",
        "endpoint",
        "management_address",
        "cloud_id",
        "cloud",
        "cloud_region_id",
        "port",
        "snmp_port",
        "brand",
        "device_type",
        "organization",
        "os_type",
        "collector_cluster_id",
        "node_id",
        "monitor_id",
    }
    permission_key = PERMISSION_TASK

    class Meta:
        model = CollectModels
        exclude = ("execution_claim_token",)
        extra_kwargs = {
            # "name": {"required": True},
            # "task_type": {"required": True},
        }

    def _get_attr_or_instance_value(self, attrs, field_name):
        value = attrs.get(field_name)
        if value is None and self.instance is not None:
            value = getattr(self.instance, field_name, None)
        return value

    def _get_effective_params(self, attrs):
        instance_params = {}
        if self.instance is not None:
            instance_params = dict(getattr(self.instance, "params", None) or {})

        raw_params = attrs.get("params")
        if raw_params is None:
            return instance_params

        params = dict(instance_params)
        params.update(dict(raw_params or {}))
        return params

    def _query_authorized_instances(self, inst_uuids):
        trusted_instances = InstanceManage.query_entity_by_uuids(inst_uuids)
        request = self.context.get("request")
        if request is None:
            raise serializers.ValidationError({"instances": "缺少实例权限上下文"})
        permission_maps = {}
        for instance in trusted_instances:
            instance_model_id = instance.get("model_id", "")
            if instance_model_id not in permission_maps:
                permission_maps[instance_model_id] = CmdbRulesFormatUtil.format_user_groups_permissions(
                    request,
                    instance_model_id,
                )
            if not InstanceManage._has_topology_view_permission(
                instance,
                permission_maps[instance_model_id],
                user=request.user,
            ):
                raise serializers.ValidationError({"instances": "部分实例不存在或缺少访问权限"})
        return trusted_instances

    @classmethod
    def _resolve_target_model_id(cls, model_id):
        collect_meta = get_collect_object_meta(model_id) or {}
        target_model_id = collect_meta.get("target_model_id")
        if target_model_id:
            return target_model_id
        if model_id in cls.STRICT_PLATFORM_TARGET_MODELS:
            return model_id
        return ""

    def _normalize_instance_identity_contract(self, raw_instances, model_id):
        if raw_instances in (None, []):
            return raw_instances

        if model_id == "ip" and isinstance(raw_instances, dict):
            if "subnet_ids" in raw_instances:
                raise serializers.ValidationError({"instances": "IP 采集任务不接受 subnet_ids，请使用 subnet_uuids"})
            subnet_uuids = raw_instances.get("subnet_uuids") or []
            if not isinstance(subnet_uuids, list) or not subnet_uuids:
                raise serializers.ValidationError({"instances": "IP 采集任务必须使用 subnet_uuids 选择子网"})
            try:
                normalized_uuids = [normalize_inst_uuid(value) for value in subnet_uuids]
            except Exception as err:  # noqa: BaseAppException
                raise serializers.ValidationError({"instances": "subnet_uuids 必须为合法 UUIDv4 列表"}) from err
            trusted_subnets = self._query_authorized_instances(normalized_uuids)
            if len(trusted_subnets) != len(normalized_uuids) or any(subnet.get("model_id") != "subnet" for subnet in trusted_subnets):
                raise serializers.ValidationError({"instances": "部分子网不存在、无权限或模型不匹配"})
            normalized = {key: copy.deepcopy(raw_instances[key]) for key in ("scan_method", "ports") if key in raw_instances}
            normalized["subnet_uuids"] = normalized_uuids
            return normalized

        if not isinstance(raw_instances, list):
            raise serializers.ValidationError({"instances": "实例目标必须为列表"})

        normalized_instances = []
        for raw_instance in raw_instances:
            if not isinstance(raw_instance, dict):
                raise serializers.ValidationError({"instances": "实例目标格式错误"})
            if "_id" in raw_instance or "inst_id" in raw_instance:
                raise serializers.ValidationError({"instances": "实例目标不接受 _id/inst_id，请使用 inst_uuid"})
            try:
                inst_uuid = normalize_inst_uuid(raw_instance.get("inst_uuid"))
            except Exception as err:  # noqa: BaseAppException
                raise serializers.ValidationError({"instances": "每个实例目标必须包含合法 inst_uuid"}) from err
            normalized_instances.append(inst_uuid)

        trusted_instances = self._query_authorized_instances(normalized_instances)
        trusted_by_uuid = {trusted.get("inst_uuid"): trusted for trusted in trusted_instances if trusted.get("inst_uuid")}
        if any(inst_uuid not in trusted_by_uuid for inst_uuid in normalized_instances):
            raise serializers.ValidationError({"instances": "部分实例不存在或缺少访问权限"})
        target_model_id = self._resolve_target_model_id(model_id)
        if target_model_id and any(trusted_by_uuid[inst_uuid].get("model_id") != target_model_id for inst_uuid in normalized_instances):
            raise serializers.ValidationError({"instances": "采集任务与平台实例模型不匹配"})
        snapshots = []
        for inst_uuid in normalized_instances:
            trusted = trusted_by_uuid[inst_uuid]
            snapshots.append(
                {key: copy.deepcopy(value) for key, value in trusted.items() if key in CollectModelSerializer.TRUSTED_INSTANCE_SNAPSHOT_FIELDS}
            )
        return snapshots

    @staticmethod
    def _should_validate_network_topology(task_type, model_id):
        return task_type == CollectPluginTypes.SNMP or model_id == "network"

    @staticmethod
    def _validate_topology_params(params):
        errors = {}

        raw_protocols = params.get("topology_protocols")
        if raw_protocols is None:
            topology_protocols = list(DEFAULT_TOPOLOGY_PROTOCOLS)
        elif not isinstance(raw_protocols, list):
            errors["topology_protocols"] = "请选择至少一种拓扑协议"
            topology_protocols = []
        else:
            topology_protocols = []
            invalid_protocols = []
            for protocol in raw_protocols:
                if protocol not in ALLOWED_TOPOLOGY_PROTOCOLS:
                    invalid_protocols.append(protocol)
                    continue
                if protocol not in topology_protocols:
                    topology_protocols.append(protocol)
            if invalid_protocols:
                errors["topology_protocols"] = f"仅支持以下拓扑协议: {', '.join(ALLOWED_TOPOLOGY_PROTOCOLS)}"

        topology_fallback_strategy = params.get("topology_fallback_strategy", DEFAULT_TOPOLOGY_FALLBACK_STRATEGY)
        if topology_fallback_strategy not in ALLOWED_TOPOLOGY_FALLBACK_STRATEGIES:
            errors["topology_fallback_strategy"] = "拓扑回退策略不合法"

        raw_min_confidence = params.get("min_confidence", DEFAULT_TOPOLOGY_MIN_CONFIDENCE)
        try:
            min_confidence = float(raw_min_confidence)
        except (TypeError, ValueError):
            errors["min_confidence"] = "置信度阈值必须是 0 到 1 之间的数字"
        else:
            if min_confidence < 0 or min_confidence > 1:
                errors["min_confidence"] = "置信度阈值必须是 0 到 1 之间的数字"

        raw_interval = params.get("topology_interval_minutes")
        interval_mode = params.get("topology_interval_mode") or "recommended"
        if interval_mode not in ("recommended", "custom"):
            errors["topology_interval_mode"] = "拓扑周期模式不合法"
        try:
            topology_interval_minutes = int(raw_interval) if raw_interval not in (None, "") else None
        except (TypeError, ValueError):
            topology_interval_minutes = None
            errors["topology_interval_minutes"] = "拓扑采集周期必须是正整数分钟"
        if topology_interval_minutes is not None and topology_interval_minutes < 1:
            errors["topology_interval_minutes"] = "拓扑采集周期最小为 1 分钟"

        if errors:
            raise serializers.ValidationError({"params": errors})

        normalized = normalize_topology_contract(
            {
                **params,
                "topology_protocols": topology_protocols,
                "topology_fallback_strategy": topology_fallback_strategy,
                "min_confidence": min_confidence,
                "topology_interval_minutes": topology_interval_minutes,
                "topology_interval_mode": interval_mode,
            }
        )
        params.update(normalized)
        return params

    @staticmethod
    def _normalize_topology_params(params):
        params.update(normalize_topology_contract(params))
        return params

    def _reject_masked_secrets_on_create(self, attrs, model_id):
        if self.instance is not None:
            return

        raw_credential = self._get_attr_or_instance_value(attrs, "credential")
        if isinstance(raw_credential, dict):
            credential_pool = [raw_credential]
        elif isinstance(raw_credential, list):
            credential_pool = raw_credential
        else:
            return

        encrypted_fields = get_collect_model_passwords(
            collect_model_id=model_id,
            driver_type=self._get_attr_or_instance_value(
                attrs,
                "driver_type",
            ),
        )
        masked_fields = sorted(
            {
                field
                for credential in credential_pool
                if isinstance(credential, dict)
                for field in encrypted_fields
                if credential.get(field) == API_SECRET_MASK
            }
        )
        if masked_fields:
            raise serializers.ValidationError({"credential": {field: "新建任务时请重新填写凭据" for field in masked_fields}})

    def _validate_influxdb_credential(self, attrs):
        instances = self._get_attr_or_instance_value(attrs, "instances")
        ip_range = self._get_attr_or_instance_value(attrs, "ip_range")
        if ip_range or not isinstance(instances, list) or len(instances) != 1:
            raise serializers.ValidationError({"instances": "InfluxDB 仅支持选择一个明确的采集端点"})

        raw_credential = self._get_attr_or_instance_value(attrs, "credential")
        if isinstance(raw_credential, dict):
            credential_pool = [copy.deepcopy(raw_credential)]
        elif isinstance(raw_credential, list):
            credential_pool = copy.deepcopy(raw_credential)
        else:
            raise serializers.ValidationError({"credential": "InfluxDB 凭据格式错误"})
        if len(credential_pool) != 1 or not isinstance(credential_pool[0], dict):
            raise serializers.ValidationError({"credential": "InfluxDB 仅支持一组连接配置"})

        credential = credential_pool[0]
        allowed_fields = {
            "credential_id",
            "scheme",
            "port",
            "verify_tls",
            "token",
            "password",  # 兼容历史 InfluxDB 任务
        }
        unknown_fields = sorted(set(credential) - allowed_fields)
        errors = {}
        if unknown_fields:
            errors["fields"] = f"不支持字段: {', '.join(unknown_fields)}"

        scheme = str(credential.get("scheme") or "http").strip().lower()
        if scheme not in {"http", "https"}:
            errors["scheme"] = "仅支持 HTTP 或 HTTPS"

        try:
            port = int(credential.get("port", 8086))
        except (TypeError, ValueError):
            port = 0
        if not 1 <= port <= 65535:
            errors["port"] = "端口必须在 1 到 65535 之间"

        verify_tls = credential.get("verify_tls", True)
        if not isinstance(verify_tls, bool):
            errors["verify_tls"] = "证书校验开关必须为布尔值"

        for secret_field in ("token", "password"):
            if secret_field in credential and not isinstance(
                credential[secret_field],
                str,
            ):
                errors[secret_field] = "Token 必须为字符串"

        if errors:
            raise serializers.ValidationError({"credential": errors})

        credential.update(
            scheme=scheme,
            port=port,
            verify_tls=verify_tls,
        )
        attrs["credential"] = [credential]

    def _validate_hwcloud_credential(self, attrs):
        raw_credential = self._get_attr_or_instance_value(attrs, "credential")
        if isinstance(raw_credential, dict):
            credential_pool = [copy.deepcopy(raw_credential)]
        elif isinstance(raw_credential, list):
            credential_pool = copy.deepcopy(raw_credential)
        else:
            raise serializers.ValidationError({"credential": "华为云凭据格式错误"})

        if len(credential_pool) != 1 or not isinstance(credential_pool[0], dict):
            raise serializers.ValidationError({"credential": "华为云仅支持一组连接凭据"})

        credential = credential_pool[0]
        project_id = credential.get("project_id")
        if not isinstance(project_id, str) or not project_id.strip():
            raise serializers.ValidationError({"credential": {"project_id": "请输入华为云 Project ID"}})
        credential["project_id"] = project_id.strip()
        attrs["credential"] = [credential]

    def _validate_platform_api_credential(self, attrs):
        raw_credential = self._get_attr_or_instance_value(attrs, "credential")
        if isinstance(raw_credential, dict):
            credential_pool = [copy.deepcopy(raw_credential)]
        elif isinstance(raw_credential, list):
            credential_pool = copy.deepcopy(raw_credential)
        else:
            raise serializers.ValidationError({"credential": "平台 API 凭据格式错误"})
        if len(credential_pool) != 1 or not isinstance(credential_pool[0], dict):
            raise serializers.ValidationError({"credential": "平台 API 仅支持一组连接凭据"})

        credential = credential_pool[0]
        legacy_username = credential.pop("accessKey", None)
        legacy_password = credential.pop("accessSecret", None)
        if not credential.get("username") and legacy_username:
            credential["username"] = legacy_username
        if not credential.get("password") and legacy_password:
            credential["password"] = legacy_password
        allowed_fields = {
            "credential_id",
            "username",
            "password",
            "port",
            "verify_tls",
        }
        unknown_fields = sorted(set(credential) - allowed_fields)
        errors = {}
        if unknown_fields:
            errors["fields"] = f"不支持字段: {', '.join(unknown_fields)}"

        username = credential.get("username")
        if not isinstance(username, str) or not username.strip():
            errors["username"] = "请输入平台 API 用户名"

        password = credential.get("password")
        if self.instance is None and (not isinstance(password, str) or not password.strip()):
            errors["password"] = "请输入平台 API 密码"
        elif password is not None and not isinstance(password, str):
            errors["password"] = "平台 API 密码必须为字符串"

        try:
            port = int(credential.get("port"))
        except (TypeError, ValueError):
            port = 0
        if not 1 <= port <= 65535:
            errors["port"] = "端口必须在 1 到 65535 之间"

        verify_tls = credential.get("verify_tls", True)
        if not isinstance(verify_tls, bool):
            errors["verify_tls"] = "证书校验开关必须为布尔值"

        if errors:
            raise serializers.ValidationError({"credential": errors})

        credential.update(
            username=username.strip(),
            port=port,
            verify_tls=verify_tls,
        )
        attrs["credential"] = [credential]

    def _validate_registered_credential(self, attrs, model_id):
        raw_credential = self._get_attr_or_instance_value(attrs, "credential")
        existing_credential = getattr(self.instance, "credential", None) if self.instance is not None else None
        try:
            attrs["credential"] = validate_collect_credential(
                model_id,
                raw_credential,
                existing_credential=existing_credential,
            )
        except CredentialContractError as err:
            raise serializers.ValidationError({"credential": err.errors}) from err

    def _normalize_winsphere_instances(self, attrs):
        credential = attrs["credential"][0]
        https_port = credential["https_port"]
        if self._get_attr_or_instance_value(attrs, "ip_range"):
            raise serializers.ValidationError({"ip_range": "WinSphere 任务不支持 IP 范围"})
        instances = self._get_attr_or_instance_value(attrs, "instances")
        if not isinstance(instances, list) or len(instances) != 1:
            raise serializers.ValidationError({"instances": "WinSphere 任务必须选择一个管理平台"})
        instance = copy.deepcopy(instances[0])
        if not isinstance(instance, dict):
            raise serializers.ValidationError({"instances": "WinSphere 管理平台格式错误"})
        try:
            management_address = normalize_winsphere_management_address(instance.get("management_address"))
        except ValueError as err:
            raise serializers.ValidationError({"instances": str(err)}) from err
        instance["management_address"] = management_address
        instance["endpoint"] = f"https://{management_address}:{https_port}"
        attrs["instances"] = [instance]

    def validate(self, attrs):  # noqa: C901
        task_type = self._get_attr_or_instance_value(attrs, "task_type")
        model_id = self._get_attr_or_instance_value(attrs, "model_id")

        if "instances" in attrs:
            attrs["instances"] = self._normalize_instance_identity_contract(
                attrs.get("instances"),
                model_id,
            )

        credential_contract = get_collect_credential_contract(model_id)
        if credential_contract:
            expected_task_type = credential_contract.get("task_type")
            expected_driver_type = credential_contract.get("driver_type")
            driver_type = self._get_attr_or_instance_value(
                attrs,
                "driver_type",
            )
            contract_errors = {}
            if expected_task_type and task_type != expected_task_type:
                contract_errors["task_type"] = "采集任务类型不符合能力契约"
            if expected_driver_type and driver_type != expected_driver_type:
                contract_errors["driver_type"] = "采集驱动类型不符合能力契约"
            if contract_errors:
                raise serializers.ValidationError(contract_errors)
        if (
            credential_contract
            and credential_contract.get("requires_enabled_collect_object")
            and not get_collect_object_meta(
                model_id,
                self._get_attr_or_instance_value(attrs, "driver_type"),
            )
        ):
            raise serializers.ValidationError({"model_id": "当前版本未启用该采集能力"})
        self._reject_masked_secrets_on_create(attrs, model_id)
        if credential_contract:
            self._validate_registered_credential(attrs, model_id)
        elif model_id == "influxdb":
            self._validate_influxdb_credential(attrs)
        elif model_id == "hwcloud":
            self._validate_hwcloud_credential(attrs)
        elif model_id in {"fusioninsight", "storage", "sangforhci"}:
            self._validate_platform_api_credential(attrs)

        if model_id == "winsphere":
            self._normalize_winsphere_instances(attrs)

        if model_id == "pc":
            params = self._get_effective_params(attrs)
            instance_params = dict(getattr(self.instance, "params", None) or {}) if self.instance is not None else {}
            try:
                attrs["params"] = validate_pc_collect_task(
                    params,
                    credential=self._get_attr_or_instance_value(attrs, "credential"),
                    timeout=self._get_attr_or_instance_value(attrs, "timeout"),
                    instance_params=instance_params,
                )
            except ValueError as err:
                raise serializers.ValidationError({"params": str(err)}) from err
            attrs["driver_type"] = CollectDriverTypes.JOB
            return attrs

        if task_type != CollectPluginTypes.CONFIG_FILE:
            params = self._get_effective_params(attrs)
            if self._should_validate_network_topology(task_type, model_id):
                if normalize_topology_contract(params)["has_network_topo"]:
                    attrs["params"] = self._validate_topology_params(params)
                else:
                    attrs["params"] = self._normalize_topology_params(params)
            return attrs

        if not self._get_attr_or_instance_value(attrs, "is_interval"):
            raise serializers.ValidationError({"scan_cycle": "配置文件采集仅支持周期执行"})

        if model_id == "network_config_file":
            params = dict(self._get_effective_params(attrs) or {})
            raw_instances = attrs.get("instances")
            if raw_instances is None and self.instance is not None:
                raw_instances = self.instance.instances
            if not raw_instances:
                raise serializers.ValidationError("请选择网络设备")

            validated_instances = []
            for instance in raw_instances:
                try:
                    # P2-2.1: validate 只校验不返回,显式 normalize 后放进结果列表
                    # (落库时需要 host / device_type 字段,供下游 node_config 复用)
                    validate_network_config_instance(instance)
                    validated_instances.append(normalize_network_config_instance(instance))
                except Exception as err:
                    raise serializers.ValidationError({"instances": str(err)}) from err

            config_name = (params.get("config_name") or "").strip()
            if not config_name:
                raise serializers.ValidationError({"params": "请输入配置名称"})

            try:
                commands = validate_commands(params.get("commands"))
            except Exception as err:
                raise serializers.ValidationError({"params": str(err)}) from err

            credential_items = attrs.get("credential")
            if credential_items is None and self.instance is not None:
                credential_items = self.instance.credential
            credential_pool = CollectCredentialPoolService.normalize_pool(copy.deepcopy(credential_items))
            need_enable = any(bool(item.get("enable_password")) for item in credential_pool if isinstance(item, dict))

            attrs["instances"] = validated_instances
            attrs["ip_range"] = ""
            attrs["driver_type"] = CollectDriverTypes.PROTOCOL
            attrs["params"] = {
                **params,
                "config_name": config_name,
                "commands": "\n".join(commands),
                "need_enable": need_enable,
            }
            return attrs

        raw_params = attrs.get("params")
        if raw_params is None and self.instance is not None:
            raw_params = self.instance.params

        params = dict(raw_params or {})
        file_path = (params.get("config_file_path") or "").strip()
        if not validate_absolute_path(file_path):
            raise serializers.ValidationError({"params": "请输入有效的配置文件完整绝对路径，不能填写目录"})

        params.update(
            {
                "config_file_path": file_path,
            }
        )

        raw_instances = attrs.get("instances")
        if raw_instances is None and self.instance is not None:
            raw_instances = self.instance.instances

        if not raw_instances:
            raise serializers.ValidationError("请选择主机")

        attrs["ip_range"] = ""

        attrs["params"] = params
        attrs["driver_type"] = CollectDriverTypes.JOB
        return attrs

    def to_representation(self, instance):
        """重写序列化输出"""
        representation = super().to_representation(instance)
        # 对返回的凭据中的密码字段进行脱敏处理
        credential = CollectCredentialPoolService.normalize_pool(copy.deepcopy(representation.get("credential")))
        encrypted_fields = get_collect_model_passwords(collect_model_id=instance.model_id, driver_type=instance.driver_type)
        for item in credential:
            if not isinstance(item, dict):
                continue
            for encrypted_field in encrypted_fields:
                if encrypted_field in item:
                    item[encrypted_field] = "******"

        representation["credential"] = credential

        if self._should_validate_network_topology(instance.task_type, instance.model_id):
            raw_params = dict(representation.get("params") or {})
            representation["params"] = self._normalize_topology_params(raw_params)

        return representation


class CollectModelDetailSerializer(CollectModelSerializer):
    """采集任务配置详情，不内联可通过 ``info`` 接口读取的结果数据。"""

    class Meta:
        model = CollectModels
        fields = COLLECT_MODEL_DETAIL_FIELDS


class CollectModelIdStatusSerializer(AuthSerializer):
    permission_key = PERMISSION_TASK

    class Meta:
        model = CollectModels
        fields = ("model_id", "driver_type", "exec_status")


class CollectModelLIstSerializer(AuthSerializer):
    permission_key = PERMISSION_TASK
    message = serializers.SerializerMethodField()
    _should_validate_network_topology = staticmethod(CollectModelSerializer._should_validate_network_topology)
    _normalize_topology_params = staticmethod(CollectModelSerializer._normalize_topology_params)

    class Meta:
        model = CollectModels
        fields = [
            "id",
            "name",
            "task_type",
            "driver_type",
            "model_id",
            "exec_status",
            "updated_at",
            "message",
            "exec_time",
            "created_by",
            "input_method",
            "params",
            "team",
            "permissions",
            "data_cleanup_strategy",
            "expire_days",
        ]

    @staticmethod
    def get_message(instance):
        if instance.collect_digest:
            return instance.collect_digest

        data = {
            "add": 0,
            "update": 0,
            "delete": 0,
            "association": 0,
        }
        return data

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if self._should_validate_network_topology(instance.task_type, instance.model_id):
            raw_params = dict(representation.get("params") or {})
            representation["params"] = self._normalize_topology_params(raw_params)
        return representation


class OidModelSerializer(UsernameSerializer):
    class Meta:
        model = OidMapping
        fields = "__all__"
        extra_kwargs = {}
