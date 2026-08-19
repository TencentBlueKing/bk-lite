from dataclasses import dataclass

import requests

from apps.cmdb.constants.constants import STARGAZER_URL
from apps.cmdb.node_configs.config_factory import NodeParamsFactory


class StargazerCollectTriggerError(RuntimeError):
    pass


class StargazerCollectRetryableError(StargazerCollectTriggerError):
    pass


class StargazerCollectPermanentError(StargazerCollectTriggerError):
    pass


@dataclass(frozen=True)
class TriggerResult:
    status: str
    total: int = 1
    accepted: int = 1


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
