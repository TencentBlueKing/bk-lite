import os
from dataclasses import dataclass

import requests

from apps.cmdb.constants.constants import STARGAZER_URL
from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.core.logger import cmdb_logger as logger
from apps.rpc.exceptions import RpcTimeoutError
from apps.rpc.stargazer import Stargazer


class StargazerCollectTriggerError(RuntimeError):
    pass


class StargazerCollectRetryableError(StargazerCollectTriggerError):
    pass


class StargazerCollectPermanentError(StargazerCollectTriggerError):
    pass


class AccessCheckRemoteError(StargazerCollectTriggerError):
    def __init__(self, error_code):
        super().__init__(error_code)
        self.error_code = error_code


@dataclass(frozen=True)
class TriggerResult:
    status: str
    total: int = 1
    accepted: int = 1


def _access_point_item(task) -> dict:
    access_point = getattr(task, "access_point", None)
    if isinstance(access_point, list) and access_point and isinstance(access_point[0], dict):
        return access_point[0]
    if isinstance(access_point, dict):
        return access_point
    return {}


def _stargazer_namespace(task) -> str:
    item = _access_point_item(task)
    cloud_name = str(item.get("cloud_name") or item.get("cloud_region_name") or "").strip()
    if not cloud_name:
        try:
            from apps.cmdb.services.collect_service import CollectModelService

            _cloud, resolved = CollectModelService._resolve_host_cloud_meta(
                params=getattr(task, "params", None) or {},
                access_point=getattr(task, "access_point", None),
                instances=getattr(task, "instances", None),
                prefer_access_point=True,
            )
            cloud_name = str(resolved or "").strip()
        except Exception as exc:  # noqa: BLE001 - 解析失败时退回部署配置的实例名
            logger.error(
                "event=access_check_namespace_failed task_id=%s failed_stage=namespace error_type=%s",
                getattr(task, "pk", "-"),
                type(exc).__name__,
            )
            cloud_name = ""
    instance = cloud_name or os.getenv("STARGAZER_NATS_INSTANCE_ID", "default")
    return f"{instance}_stargazer"


class StargazerCollectTriggerClient:
    REQUEST_TIMEOUT_SECONDS = 15

    @staticmethod
    def _resolve_env_placeholder(value, env_config):
        if not isinstance(value, str) or not value.startswith("${") or not value.endswith("}"):
            return value
        env_name = value[2:-1]
        if env_name not in env_config:
            raise StargazerCollectPermanentError("Stargazer 首次采集凭据配置无效")
        return env_config[env_name]

    @staticmethod
    def _positive_int(value, field_name):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise StargazerCollectPermanentError(f"Stargazer 响应缺少有效的 {field_name}") from None
        if parsed <= 0:
            raise StargazerCollectPermanentError(f"Stargazer 响应中的 {field_name} 必须大于 0")
        return parsed

    def _build_request(self, task):
        node_params = NodeParamsFactory.get_node_params(task)
        raw_headers = node_params.custom_headers()
        env_config = node_params.env_config() or {}
        collect_headers = {key: self._resolve_env_placeholder(value, env_config) for key, value in raw_headers.items() if key.startswith("cmdb")}
        tags = getattr(node_params, "tags", {}) or {}
        headers = {
            **collect_headers,
            "instance_id": str(tags.get("instance_id") or ""),
            "instance_type": str(tags.get("instance_type") or ""),
            "collect_type": str(tags.get("collect_type") or "http"),
            "config_type": str(tags.get("config_type") or task.model_id),
        }
        url = f"{STARGAZER_URL.rstrip('/')}/api/collect/collect_info"
        return url, {}, headers

    def _parse_success(self, response):
        task_count = response.headers.get("X-Task-Count")
        if task_count is not None:
            total = self._positive_int(task_count, "X-Task-Count")
            try:
                accepted = int(response.headers.get("X-Success-Count") or 0)
            except (TypeError, ValueError):
                raise StargazerCollectPermanentError("Stargazer 响应缺少有效的 X-Success-Count") from None
            if accepted != total:
                raise StargazerCollectPermanentError(f"Stargazer 批量接收不完整: accepted={accepted}, total={total}")
            return TriggerResult("accepted", total, accepted)

        status = str(response.headers.get("X-Task-Status") or "").lower()
        if status == "queued":
            return TriggerResult("accepted")
        if status == "skipped":
            return TriggerResult("deduplicated")
        raise StargazerCollectPermanentError(f"Stargazer 未接受采集任务: status={status or 'unknown'}")

    def admit_access_check(self, task, check_id):
        """NATS 请求 Stargazer access_check，只取接纳结果。"""
        try:
            _url, _params, headers = self._build_request(task)
            body = {key[4:]: value for key, value in headers.items() if key.startswith("cmdb")}
            body["tags"] = {
                "instance_id": headers.get("instance_id") or "",
                "instance_type": headers.get("instance_type") or "",
                "collect_type": headers.get("collect_type") or "",
                "config_type": headers.get("config_type") or "",
            }
            body["check_id"] = str(check_id)
            body["collect_task_id"] = str(task.pk)
            body.pop("run_purpose", None)
            namespace = _stargazer_namespace(task)
            response = Stargazer(instance_id=namespace).client.request(
                "access_check",
                _timeout=10,
                **body,
            )
        except AccessCheckRemoteError:
            raise
        except RpcTimeoutError as exc:
            raise AccessCheckRemoteError("stargazer_timeout") from exc
        except Exception as exc:
            raise AccessCheckRemoteError("stargazer_unavailable") from exc
        if not isinstance(response, dict) or not response.get("success"):
            raise AccessCheckRemoteError("stargazer_unavailable")
        status = str(response.get("status") or "")
        if status == "accepted":
            return status
        if status == "busy":
            raise AccessCheckRemoteError("check_busy")
        raise AccessCheckRemoteError("stargazer_unavailable")

    def trigger(self, task):
        try:
            url, params, headers = self._build_request(task)
        except StargazerCollectTriggerError:
            raise
        except Exception:
            raise StargazerCollectPermanentError("Stargazer 首次采集请求配置无效") from None

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )
        except (
            requests.Timeout,
            requests.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.RetryError,
        ):
            raise StargazerCollectRetryableError("Stargazer 首次采集请求发生可重试网络错误") from None
        except requests.RequestException:
            raise StargazerCollectPermanentError("Stargazer 首次采集请求失败") from None

        if response.status_code >= 500:
            raise StargazerCollectRetryableError(f"Stargazer 首次采集请求返回 HTTP {response.status_code}")
        if response.status_code != 200:
            raise StargazerCollectPermanentError(f"Stargazer 首次采集请求返回 HTTP {response.status_code}")
        return self._parse_success(response)

    def _request(self, headers):
        url = f"{STARGAZER_URL.rstrip('/')}/api/collect/collect_info"
        try:
            return requests.get(
                url,
                headers=headers,
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )
        except (
            requests.Timeout,
            requests.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.RetryError,
        ):
            raise StargazerCollectRetryableError("Stargazer 采集请求发生可重试网络错误") from None
        except requests.RequestException:
            raise StargazerCollectPermanentError("Stargazer 采集请求失败") from None

    def admit_scan_discover(self, body):
        url = f"{STARGAZER_URL.rstrip('/')}/api/collect/scan_discover"
        try:
            response = requests.post(
                url,
                json=body or {},
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )
        except (
            requests.Timeout,
            requests.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.RetryError,
        ):
            raise StargazerCollectRetryableError("Stargazer 扫描发现请求发生可重试网络错误") from None
        except requests.RequestException:
            raise StargazerCollectPermanentError("Stargazer 扫描发现请求失败") from None

        status = str(response.headers.get("X-Task-Status") or "").lower()
        if response.status_code == 429 or status == "busy":
            raise StargazerCollectRetryableError(f"Stargazer 扫描繁忙: HTTP {response.status_code}")
        if response.status_code >= 500:
            raise StargazerCollectRetryableError(f"Stargazer 扫描发现请求返回 HTTP {response.status_code}")
        if response.status_code != 202:
            raise StargazerCollectPermanentError(f"Stargazer 未按 202 接纳扫描发现: HTTP {response.status_code} status={status or 'unknown'}")
        if status not in {"accepted", "duplicate_active"}:
            raise StargazerCollectPermanentError(f"Stargazer 未接受扫描发现: status={status or 'unknown'}")
        total = self._positive_int(response.headers.get("X-Target-Count"), "X-Target-Count")
        result_status = "duplicate" if status == "duplicate_active" else "accepted"
        return TriggerResult(result_status, total, total)

    def admit(self, headers):
        """按 Stargazer 当前契约接纳一枪：202 + X-Target-Count。不改 trigger() 的旧解析。"""
        try:
            response = self._request(headers)
        except StargazerCollectTriggerError:
            raise

        status = str(response.headers.get("X-Task-Status") or "").lower()
        if response.status_code == 429 or status == "busy":
            raise StargazerCollectRetryableError(f"Stargazer 采集繁忙: HTTP {response.status_code}")
        if response.status_code >= 500:
            raise StargazerCollectRetryableError(f"Stargazer 采集请求返回 HTTP {response.status_code}")
        if response.status_code != 202:
            raise StargazerCollectPermanentError(f"Stargazer 未按 202 接纳扫描: HTTP {response.status_code} status={status or 'unknown'}")
        if status not in {"accepted", "duplicate_active"}:
            raise StargazerCollectPermanentError(f"Stargazer 未接受扫描任务: status={status or 'unknown'}")
        total = self._positive_int(response.headers.get("X-Target-Count"), "X-Target-Count")
        result_status = "duplicate" if status == "duplicate_active" else "accepted"
        return TriggerResult(result_status, total, total)
