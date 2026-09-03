from apps.cmdb.services.instance_identity import normalize_inst_uuid
from apps.core.exceptions.base_app_exception import BaseAppException


class ConfigArtifactNodeParamsMixin:
    """配置制品采集的共用下发边界：一个目标对应一个 Telegraf 子配置。"""

    _active_target_instance = None

    @property
    def drop_trigger_metric(self):
        return True

    def _target_instances(self):
        return [item for item in (self.instance.instances or []) if isinstance(item, dict)]

    def _current_target_instance(self):
        if self._active_target_instance is not None:
            return self._active_target_instance
        targets = self._target_instances()
        return targets[0] if targets else {}

    @staticmethod
    def _target_uuid(target):
        raw_uuid = target.get("inst_uuid") if isinstance(target, dict) else None
        if not raw_uuid:
            raise BaseAppException("配置文件采集目标缺少实例 UUID")
        return normalize_inst_uuid(raw_uuid)

    @property
    def config_id(self):
        target_uuid = self._target_uuid(self._current_target_instance())
        return f"{self.metric_scope_id}_{target_uuid.replace('-', '')}"

    def push_params(self):
        nodes = []
        try:
            for target in self._target_instances():
                self._active_target_instance = target
                nodes.extend(super().push_params())
        finally:
            self._active_target_instance = None
        return nodes

    def delete_params(self):
        config_ids = [self.metric_scope_id]
        try:
            for target in self._target_instances():
                self._active_target_instance = target
                config_ids.append(self.config_id)
        finally:
            self._active_target_instance = None
        return list(dict.fromkeys(config_ids))
