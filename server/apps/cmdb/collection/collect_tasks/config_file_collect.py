import requests

from apps.cmdb.constants.constants import STARGAZER_URL
from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.config_file_service import ConfigFileService
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger


class ConfigFileCollect(object):
    """配置文件采集即时触发协调器。"""

    def __init__(self, task_id: int, task=None):
        self.task = task or CollectModels.objects.get(id=task_id)
        self.params = dict(self.task.params or {})
        self.file_path = self.params.get("config_file_path", "")

    def _build_trigger_request(self) -> tuple[str, dict, dict, int]:
        node_params = NodeParamsFactory.get_node_params(self.task)
        raw_headers = node_params.custom_headers()
        params = {k.split("cmdb", 1)[-1]: v for k, v in raw_headers.items() if k.startswith("cmdb")}
        tags = getattr(node_params, "tags", {})
        headers = {
            "X-Instance-ID": str(tags.get("instance_id") or ""),
            "X-Instance-Type": str(tags.get("instance_type") or ""),
            "X-Collect-Type": str(tags.get("collect_type") or "http"),
            "X-Config-Type": str(tags.get("config_type") or self.task.model_id),
        }
        request_timeout = max(int(self.task.timeout or 0), 10)
        url = f"{STARGAZER_URL.rstrip('/')}/api/collect/collect_info"
        return url, params, headers, request_timeout

    @staticmethod
    def _parse_positive_int(value, field_name: str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as err:
            raise BaseAppException(f"配置文件采集触发响应缺少有效的 {field_name}") from err
        if parsed <= 0:
            raise BaseAppException(f"配置文件采集触发响应中的 {field_name} 必须大于 0")
        return parsed

    @classmethod
    def _validate_trigger_response(cls, response):
        task_status = str(response.headers.get("X-Task-Status") or "").strip().lower()
        task_count = response.headers.get("X-Task-Count")
        success_count = response.headers.get("X-Success-Count")

        if task_count is not None:
            total = cls._parse_positive_int(task_count, "X-Task-Count")
            success = int(success_count or 0)
            if success != total:
                raise BaseAppException(f"配置文件采集触发不完整: accepted={success}, total={total}")
            return

        if task_status in {"queued", "skipped"}:
            return

        raise BaseAppException(f"配置文件采集触发失败: {task_status or 'unknown'}")

    def _trigger_remote_collection(self):
        url, params, headers, request_timeout = self._build_trigger_request()
        try:
            response = requests.get(url, params=params, headers=headers, timeout=request_timeout)
        except requests.Timeout as err:
            raise BaseAppException(f"配置文件采集触发超时: {str(err)}") from err
        except requests.RequestException as err:
            raise BaseAppException(f"配置文件采集触发失败: {str(err)}") from err

        if response.status_code != 200:
            raise BaseAppException(
                f"配置文件采集触发失败，Stargazer 返回 {response.status_code}: {response.text}"
            )

        self._validate_trigger_response(response)

    def __call__(self):
        logger.info(
            "[ConfigFileCollect] 触发配置文件采集 task_id=%s, path=%s, instance=%s",
            self.task.id,
            self.file_path,
            self.task.instances,
        )
        self._trigger_remote_collection()
        return ConfigFileService.build_pending_result(self.task)
