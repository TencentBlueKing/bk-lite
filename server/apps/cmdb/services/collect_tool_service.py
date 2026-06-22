# -- coding: utf-8 --
# @File: collect_tool_service.py
# @Time: 2026/05/08
import re
import uuid

from django.conf import settings
from django.core.cache import cache
from rest_framework.exceptions import ValidationError

from apps.cmdb.models.collect_model import CollectModels
from apps.rpc.stargazer import Stargazer
from apps.core.utils.team_utils import get_current_team

MASKED_PASSWORD = "••••••"

TIMEOUT_MAP = {
    "test_connection": 10,
    "raw_collect": 300,
    "get_oid": 120,
    "ipmi_collect": 30,
}

# SNMP protocol credential password fields
SNMP_PASSWORD_FIELDS = {"community", "authkey", "privkey"}
# IPMI protocol credential password fields
IPMI_PASSWORD_FIELDS = {"password"}
COLLECT_TOOL_DEBUG_CACHE_PREFIX = "collect_tool_debug:"
COLLECT_TOOL_DEBUG_CACHE_TTL = 3600
COLLECT_TOOL_POLL_INTERVAL_MS = 2000


class CollectToolService:
    @staticmethod
    def build_debug_owner(request) -> dict:
        return {
            "username": getattr(request.user, "username", ""),
            "domain": getattr(request.user, "domain", ""),
        }

    @staticmethod
    def build_node_permission_data(request) -> dict:
        include_children = str(request.COOKIES.get("include_children", "0")).lower() in {"1", "true", "yes"}
        return {
            "username": getattr(request.user, "username", ""),
            "domain": getattr(request.user, "domain", ""),
            "current_team": get_current_team(request),
            "include_children": include_children,
        }

    @staticmethod
    def can_access_debug_state(state: dict, request) -> bool:
        owner = state.get("owner") or {}
        return owner.get("username") == getattr(request.user, "username", None) and owner.get("domain") == getattr(request.user, "domain", None)

    @staticmethod
    def get_accessible_task(request, task_id: int, operator: str = "View") -> CollectModels:
        from apps.cmdb.permissions.inst_task_permission import InstanceTaskPermission

        try:
            instance = CollectModels.objects.get(id=task_id)
        except CollectModels.DoesNotExist:
            raise ValidationError(f"task_id={task_id} 对应任务不存在")

        permission_checker = InstanceTaskPermission()
        action = "exec_task" if operator == "Operator" else "retrieve"
        view = type(
            "CollectToolPermissionView",
            (),
            {"action": action, "operator_actions": permission_checker.operator_actions},
        )()

        if not permission_checker.has_object_permission(request, view, instance):
            raise ValidationError("抱歉！您没有访问该采集任务的权限")

        return instance

    @staticmethod
    def create_debug_id() -> str:
        return f"dbg_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def get_timeout(action: str) -> int:
        """按 TIMEOUT_MAP 返回写死的 timeout 秒数。"""
        return TIMEOUT_MAP.get(action, 10)

    @staticmethod
    def get_cache_key(debug_id: str) -> str:
        return f"{COLLECT_TOOL_DEBUG_CACHE_PREFIX}{debug_id}"

    @staticmethod
    def save_debug_state(debug_id: str, status: str, result: dict | None = None, owner: dict | None = None) -> dict:
        state = {
            "debug_id": debug_id,
            "status": status,
            "poll_interval_ms": COLLECT_TOOL_POLL_INTERVAL_MS,
        }
        if owner is not None:
            state["owner"] = owner
        else:
            previous = cache.get(CollectToolService.get_cache_key(debug_id)) or {}
            if previous.get("owner"):
                state["owner"] = previous["owner"]
        if result is not None:
            state["result"] = result
        cache.set(CollectToolService.get_cache_key(debug_id), state, timeout=COLLECT_TOOL_DEBUG_CACHE_TTL)
        return state

    @staticmethod
    def get_debug_state(debug_id: str) -> dict | None:
        return cache.get(CollectToolService.get_cache_key(debug_id))

    @staticmethod
    def build_submit_response(debug_id: str, status: str, result: dict | None = None) -> dict:
        response = {
            "debug_id": debug_id,
            "status": status,
            "poll_interval_ms": COLLECT_TOOL_POLL_INTERVAL_MS,
        }
        if result is not None:
            response["result"] = result
        return response

    @staticmethod
    def build_error_result(
        debug_id: str,
        payload: dict,
        stage: str,
        summary: str,
        raw_log: str = "",
        duration_ms: int = 0,
    ) -> dict:
        return {
            "request_id": debug_id,
            "protocol": payload.get("protocol"),
            "action": payload.get("action"),
            "executor": "stargazer",
            "success": False,
            "stage": stage,
            "summary": summary,
            "raw_log": raw_log,
            "duration_ms": duration_ms,
            "meta": {"target": payload.get("target"), "port": payload.get("port")},
        }

    @staticmethod
    def resolve_access_point(request, access_point_id: str) -> str:
        """
        查询接入点对应的 cloud_name，组装 Stargazer service_name。
        复用与 collect_service.list_regions 相同的路由逻辑。
        """
        try:
            from apps.node_mgmt.models.sidecar import Node
            from apps.rpc.node_mgmt import NodeMgmt

            permission_data = CollectToolService.build_node_permission_data(request)
            authorized_nodes = NodeMgmt().get_authorized_nodes_by_ids([access_point_id], permission_data)
            if not authorized_nodes:
                raise ValidationError("抱歉！您没有访问该接入点的权限")

            node = Node.objects.filter(id=access_point_id).first()
            if not node:
                raise ValidationError(f"接入点 {access_point_id} 不存在")

            cloud_region = node.cloud_region if hasattr(node, "cloud_region") else None
            cloud_name = ""
            if cloud_region:
                cloud_name = getattr(cloud_region, "name", "") or ""

            if not cloud_name:
                # 尝试通过 cloud_region_id 查询
                cloud_region_id = getattr(node, "cloud_region_id", None)
                if cloud_region_id:
                    from apps.node_mgmt.models.cloud_region import CloudRegion

                    cr = CloudRegion.objects.filter(id=cloud_region_id).first()
                    if cr:
                        cloud_name = cr.name or ""

            if not cloud_name:
                cloud_name = "default"
            # if settings.DEBUG:
            #     cloud_name = f"{cloud_name}_local"
            return f"{cloud_name}_stargazer"
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"解析接入点失败: {e}")

    @staticmethod
    def inject_credentials(payload: dict, instance: CollectModels) -> dict:
        """
        若 payload 中密码字段为 MASKED_PASSWORD 且 task_id 有效：
        从 CollectModels(id=task_id).decrypt_credentials 取对应字段明文并替换。
        """
        decrypted = instance.decrypt_credentials or {}
        credential = payload.get("credential", {})
        protocol = payload.get("protocol")

        if protocol == "snmp":
            password_fields = SNMP_PASSWORD_FIELDS
        else:
            password_fields = IPMI_PASSWORD_FIELDS

        for field in password_fields:
            if credential.get(field) == MASKED_PASSWORD:
                if field in decrypted:
                    credential[field] = decrypted[field]
                else:
                    raise ValidationError(f"无法从原任务获取字段 {field} 的凭据")

        payload["credential"] = credential
        return payload

    @staticmethod
    def execute_debug(payload: dict, service_name: str, timeout: int, request_id: str | None = None) -> dict:
        """
        调用 Stargazer RPC，同步等待结果。
        NATS request timeout = timeout + 5s。
        返回标准化后的响应 dict（附加 request_id, executor, meta）。
        """
        request_id = request_id or CollectToolService.create_debug_id()
        protocol = payload["protocol"]
        action = payload["action"]
        target = payload["target"]
        port = payload["port"]

        # Build NATS payload (without access_point_id, with timeout injected)
        nats_payload = {
            "protocol": protocol,
            "action": action,
            "target": target,
            "port": port,
            "timeout": timeout,
            "credential": payload.get("credential", {}),
        }
        if protocol == "snmp" and action == "get_oid" and payload.get("oid"):
            nats_payload["oid"] = payload["oid"]

        try:
            stargazer = Stargazer(instance_id=service_name)
            result = stargazer.collection_tool_debug(nats_payload, timeout)
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                result = {
                    "success": False,
                    "stage": "timeout",
                    "summary": f"请求超时: Stargazer 未在 {timeout}s 内响应",
                    "raw_log": "",
                    "duration_ms": timeout * 1000,
                }
            else:
                result = {
                    "success": False,
                    "stage": "unknown",
                    "summary": f"调用 Stargazer 失败: {error_msg}",
                    "raw_log": "",
                    "duration_ms": 0,
                }

        result = CollectToolService.normalize_debug_result(result)

        return {
            "request_id": request_id,
            "protocol": protocol,
            "action": action,
            "executor": "stargazer",
            "success": result.get("success", False),
            "stage": result.get("stage"),
            "summary": result.get("summary"),
            "raw_log": result.get("raw_log", ""),
            "duration_ms": result.get("duration_ms", 0),
            "meta": {"target": target, "port": port},
        }

    @staticmethod
    def normalize_debug_result(result: dict) -> dict:
        success = result.get("success", False)
        summary = result.get("summary")
        raw_log = result.get("raw_log", "")
        error_message = result.get("error")

        if not success and error_message:
            if not summary:
                summary = str(error_message)
            if not raw_log:
                raw_log = str(error_message)

        normalized_result = dict(result)
        normalized_result["summary"] = summary
        normalized_result["raw_log"] = raw_log
        if not success and not normalized_result.get("stage"):
            normalized_result["stage"] = "unknown"
        return normalized_result

    @staticmethod
    def enqueue_debug_task(debug_id: str, payload: dict, service_name: str, timeout: int, owner: dict) -> None:
        from apps.cmdb.tasks.celery_tasks import execute_collect_tool_debug_task

        CollectToolService.save_debug_state(debug_id, "pending", owner=owner)
        execute_collect_tool_debug_task.delay(debug_id, payload, service_name, timeout)

    @staticmethod
    def run_debug_task(debug_id: str, payload: dict, service_name: str, timeout: int) -> dict:
        CollectToolService.save_debug_state(debug_id, "running")
        result = CollectToolService.execute_debug(
            payload=payload,
            service_name=service_name,
            timeout=timeout,
            request_id=debug_id,
        )
        final_status = "success" if result.get("success") else "error"
        CollectToolService.save_debug_state(debug_id, final_status, result)
        return result

    @staticmethod
    def _build_access_point_prefill(instance: CollectModels) -> dict:
        access_point_data = instance.access_point
        if isinstance(access_point_data, list) and access_point_data:
            access_point_data = access_point_data[0]

        if not isinstance(access_point_data, dict):
            return {}

        access_point_id = access_point_data.get("id", "") or access_point_data.get("node_id", "")
        access_point_name = access_point_data.get("name", "") or access_point_data.get("node_name", "")
        if not access_point_id and not access_point_name:
            return {}

        return {
            "access_point": {
                "id": str(access_point_id),
                "name": str(access_point_name),
            }
        }

    @staticmethod
    def _extract_target_context(instance: CollectModels) -> tuple[str | None, int | None]:
        target_host = None
        target_port = None
        instances_data = instance.instances or []

        if instances_data and isinstance(instances_data, list):
            first_inst = instances_data[0]
            if isinstance(first_inst, dict):
                target_host = first_inst.get("ip") or first_inst.get("host")
                target_port = first_inst.get("port")

        if not target_host and instance.ip_range:
            ip_range = instance.ip_range.strip()
            first_ip = ip_range.split("\n")[0].strip().split(",")[0].strip()
            if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", first_ip):
                target_host = first_ip

        return target_host, target_port

    @staticmethod
    def _get_decrypted_credential(instance: CollectModels) -> dict:
        decrypted_cred = instance.decrypt_credentials or {}
        if not decrypted_cred and isinstance(instance.credential, dict):
            return dict(instance.credential)
        return decrypted_cred

    @staticmethod
    def _build_snmp_prefill(decrypted_cred: dict, credential: dict, target_port: int | None) -> tuple[dict, int]:
        cred_prefill = {}
        version = decrypted_cred.get("version") or credential.get("version")
        port = int(target_port or decrypted_cred.get("snmp_port") or decrypted_cred.get("port") or 161)

        if not version:
            return cred_prefill, port

        cred_prefill["version"] = version

        if version in ("v2", "v2c"):
            if decrypted_cred.get("community"):
                cred_prefill["community"] = MASKED_PASSWORD
            return cred_prefill, port

        if version != "v3":
            return cred_prefill, port

        for field in ("username", "level", "integrity"):
            value = decrypted_cred.get(field)
            if value:
                cred_prefill[field] = value

        for masked_field in ("authkey", "privkey"):
            if decrypted_cred.get(masked_field):
                cred_prefill[masked_field] = MASKED_PASSWORD

        if cred_prefill.get("level") == "authPriv" and decrypted_cred.get("privacy"):
            cred_prefill["privacy"] = decrypted_cred["privacy"]

        return cred_prefill, port

    @staticmethod
    def _build_ipmi_prefill(decrypted_cred: dict, target_port: int | None) -> tuple[dict, int]:
        cred_prefill = {}
        port = int(decrypted_cred.get("port") or target_port or 623)

        username = decrypted_cred.get("username")
        if username:
            cred_prefill["username"] = username
        if decrypted_cred.get("password"):
            cred_prefill["password"] = MASKED_PASSWORD
        if decrypted_cred.get("privilege"):
            cred_prefill["privilege"] = decrypted_cred["privilege"]
        if decrypted_cred.get("cipher_suite"):
            cred_prefill["cipher_suite"] = str(decrypted_cred["cipher_suite"])

        return cred_prefill, port

    @staticmethod
    def build_prefill(instance: CollectModels, task_id: int, protocol: str) -> dict:
        """
        从 CollectModels 读取任务快照，提取可填字段。
        密码字段脱敏。返回 prefill dict，can_prefill=false 时只返回粗粒度提示。
        """
        credential = instance.credential or {}
        prefill = CollectToolService._build_access_point_prefill(instance)
        target_host, target_port = CollectToolService._extract_target_context(instance)
        if target_host:
            prefill["target"] = target_host

        decrypted_cred = CollectToolService._get_decrypted_credential(instance)

        if protocol == "snmp":
            cred_prefill, port = CollectToolService._build_snmp_prefill(decrypted_cred, credential, target_port)
            prefill["port"] = port
        elif protocol == "ipmi":
            cred_prefill, port = CollectToolService._build_ipmi_prefill(decrypted_cred, target_port)
            prefill["port"] = port
        else:
            cred_prefill = {}

        if cred_prefill:
            prefill["credential"] = cred_prefill

        if not prefill:
            return {"task_id": task_id, "protocol": protocol, "can_prefill": False, "prefill": None}

        return {
            "task_id": task_id,
            "protocol": protocol,
            "can_prefill": True,
            "prefill": prefill,
        }
