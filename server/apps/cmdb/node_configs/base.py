# -- coding: utf-8 --
# @File: base.py
# @Time: 2025/11/13 14:16
# @Author: windyzhao
import os
import json
from abc import abstractmethod, ABCMeta

from django.conf import settings
from jinja2 import FileSystemLoader, DebugUndefined
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.safe_template import build_sandboxed_env


class BaseNodeParams(metaclass=ABCMeta):
    PLUGIN_MAP = {}  # 插件名称映射
    plugin_name = None
    # registry key = (model_id, driver_type)
    # 同一个 model（例如 physcial_server）可以同时存在 SSH/job 和 IPMI/protocol 两条下发链路。
    _registry = {}  # 自动收集支持的 model_id 对应的子类
    interval = 300  # 默认的采集间隔时间（秒）
    MIN_INTERVAL_SECONDS = 60

    @classmethod
    def build_registry_key(cls, model_id, driver_type=None):
        return model_id, driver_type

    @classmethod
    def normalize_model_id(cls, model_id):
        if not model_id:
            return model_id
        return model_id.replace("_account", "")

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        plugin_name = getattr(cls, "plugin_name", None)
        model_id = getattr(cls, "supported_model_id", None)
        driver_type = getattr(cls, "supported_driver_type", None)
        if model_id and plugin_name:
            registry_key = cls.build_registry_key(model_id, driver_type)
            BaseNodeParams._registry[registry_key] = cls
            BaseNodeParams.PLUGIN_MAP.update({registry_key: plugin_name})
        else:
            logger.warning(
                f"子类 {cls.__name__} 未正确设置 'supported_model_id' 或 'plugin_name' 属性，将不会被注册到 BaseNodeParams 中。"
            )

    def __init__(self, instance):
        self.instance = instance
        self.model_id = instance.model_id  # 当出现多对象采集的时候这个model_id就不能准确的标识唯一的model_id
        raw_credential = self.instance.decrypt_credentials or {}
        self.credential_pool = raw_credential if isinstance(raw_credential, list) else ([raw_credential] if raw_credential else [])
        # 节点管理仍沿用“单凭据 + 一批目标”契约；多凭据任务下发配置时默认取首凭据保持兼容。
        if isinstance(raw_credential, list):
            raw_credential = raw_credential[0] if raw_credential else {}
        self.credential = raw_credential
        self.base_path = "${STARGAZER_URL}/api/collect/collect_info"
        # 只有当子类没有定义 host_field 类属性时才设置默认值,避免覆盖子类定义
        if not hasattr(self.__class__, 'host_field'):
            self.host_field = "ip_addr"  # 默认的 ip字段 若不一样重新定义
        self.timeout = instance.timeout
        self.response_timeout = 10
        self.executor_type = "protocol"  # 默认执行器类型
        self.has_network_topo = bool(self.instance.params.get("has_network_topo"))  # 是否包含网络拓扑采集

    def get_hosts(self):
        """
        返回IP段或者IP列表
        """
        if self.instance.instances:
            hosts = ",".join(instance.get(self.host_field, "") for instance in self.instance.instances)
        else:
            hosts = self.instance.ip_range
        return "hosts", hosts

    @property
    def model_plugin_name(self):
        """
        获取插件名称，如果找不到则抛出异常
        """
        normalized_model_id = self.normalize_model_id(self.model_id)
        candidate_keys = [
            self.build_registry_key(self.model_id, self.instance.driver_type),
            self.build_registry_key(normalized_model_id, self.instance.driver_type),
            self.build_registry_key(self.model_id),
            self.build_registry_key(normalized_model_id),
        ]

        for registry_key in dict.fromkeys(candidate_keys):
            plugin_name = self.PLUGIN_MAP.get(registry_key)
            if plugin_name:
                return plugin_name

        raise KeyError(
            f"未在 PLUGIN_MAP 中找到对应 {self.model_id} / {self.instance.driver_type} 的插件配置")

    @abstractmethod
    def set_credential(self, *args, **kwargs):
        """
        生成凭据
        TODO 后续会有多凭据 后边再改
        """
        raise NotImplementedError

    @classmethod
    def build_region_credential(cls, raw_credential):
        return raw_credential or {}

    def env_config(self, *args, **kwargs):
        """
        生成环境变量配置
        """
        raise NotImplementedError

    def build_credentials_pool(self):
        return []

    @property
    def has_multiple_credentials(self):
        return len(self.credential_pool or []) > 1

    @staticmethod
    def strip_flattened_credential_fields(params, credentials_pool):
        if not isinstance(params, dict) or not credentials_pool:
            return params
        credential_fields = set()
        for credential in credentials_pool:
            if isinstance(credential, dict):
                credential_fields.update(credential.keys())
        for field_name in credential_fields:
            params.pop(field_name, None)
        return params

    @staticmethod
    def flatten_credentials_pool(credentials_pool):
        flattened = {}
        if not credentials_pool:
            return flattened
        flattened["credential_count"] = len(credentials_pool)
        for index, credential in enumerate(credentials_pool):
            if not isinstance(credential, dict):
                continue
            for field_name, field_value in credential.items():
                if field_value in (None, ""):
                    continue
                flattened[f"credential_{index}_{field_name}"] = field_value
        return flattened

    @property
    def tags(self):
        tags = {
            "instance_id": self._instance_id,
            "instance_type": self.get_instance_type,
            "collect_type": "http",
            "config_type": self.model_id,
        }
        return tags

    def custom_headers(self):
        """
        格式化服务器的路径
        """
        # 加入配置的唯一ID
        _model_id = getattr(self, "supported_model_id", self.model_id)
        # 加入ip字段和值
        ip_addr_field, ip_addrs = self.get_hosts()
        params = self.set_credential()
        # 加入插件信息
        params.update(
            {
                "plugin_name": self.model_plugin_name,
                ip_addr_field: ip_addrs,
                "executor_type": self.executor_type,
                "model_id": _model_id,
                "timeout": self.timeout,
                "collect_task_id": self.instance.id,
                "credential_result_subject": "receive_collect_credential_result",
            }
        )
        credentials_pool = self.build_credentials_pool()
        if credentials_pool:
            if self.has_multiple_credentials:
                params = self.strip_flattened_credential_fields(params, credentials_pool)
            params.update(self.flatten_credentials_pool(credentials_pool))
        _params = {f"cmdb{k}": str(v) for k, v in params.items()}
        # 加入tags 冗余一份
        _params.update(self.tags)
        return _params

    @property
    def get_instance_type(self):
        if self.model_id == "vmware_vc":
            instance_type = "vmware"
        else:
            instance_type = self.model_id
        return f"cmdb_{instance_type}"

    @property
    def _instance_id(self):
        """
        实例ID
        采集配置在节点管理中的唯一标识
        """
        return f"cmdb_{self.instance.id}"

    @property
    def resolved_interval(self) -> int:
        """节点侧采集间隔：优先跟随任务周期，异常时回退类默认值。"""
        cycle_value_type = getattr(self.instance, "cycle_value_type", "")
        cycle_value = getattr(self.instance, "cycle_value", None)
        if cycle_value_type == "cycle":
            try:
                interval_seconds = int(cycle_value) * 60
            except (TypeError, ValueError):
                interval_seconds = 0
            if interval_seconds >= self.MIN_INTERVAL_SECONDS:
                return interval_seconds
        return self.interval

    def push_params(self):
        """
        生成节点管理创建配置的参数
        """
        if self.plugin_name is None:
            raise ValueError("插件名称未设置，请检查 plugin_name 是否正确")

        nodes = []
        node = self.instance.access_point[0]
        content = {
            "instance_id": self._instance_id,
            "interval": self.resolved_interval,
            "instance_type": self.get_instance_type,
            "timeout": self.timeout,
            "response_timeout": self.response_timeout,
            "headers": self.custom_headers(),
            "config_type": self.model_id,
        }
        jinja_context = self.render_template(context=content)
        nodes.append({
            "id": self._instance_id,
            "collect_type": "http",
            "type": self.model_id,
            "content": jinja_context,
            "node_id": node["id"],
            "collector_name": "Telegraf",
            "env_config": self.env_config()
        })
        return nodes

    # 类级别缓存沙箱环境
    _jinja_env = None

    @classmethod
    def get_jinja_env(cls):
        """延迟初始化并缓存安全的 Jinja2 沙箱环境"""
        if cls._jinja_env is None:
            template_dir = os.path.join(settings.BASE_DIR, "apps/cmdb/support-files")
            cls._jinja_env = build_sandboxed_env(
                loader=FileSystemLoader(template_dir),
                undefined=DebugUndefined,
                extra_filters={"to_toml": cls.to_toml_dict, "default": cls.jinja_default},
            )
        return cls._jinja_env

    @staticmethod
    def escape_toml_string(s: str) -> str:
        """转义 TOML 字符串中的特殊字符"""
        if not isinstance(s, str):
            s = str(s)
        return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')

    @staticmethod
    def to_toml_dict(d):
        """将字典转换为 TOML 格式的内联表（带转义）"""
        if not d:
            return "{}"
        escaped = {k: BaseNodeParams.escape_toml_string(v) for k, v in d.items()}
        return "{ " + ", ".join(f'"{k}" = "{v}"' for k, v in escaped.items()) + " }"

    @staticmethod
    def jinja_default(value, default_value="", use_falsey=False):
        """为节点模板提供最小兼容的 default filter。"""
        if value is None:
            return default_value
        if use_falsey and not value:
            return default_value
        return value

    def render_template(self, context: dict):
        """
        渲染指定目录下的 j2 模板文件。

        使用 SandboxedEnvironment 防止 SSTI 攻击。

        :param context: 用于模板渲染的变量字典
        :return: 渲染后的配置字符串
        """
        file_name = "base.child.toml.j2"
        env = self.get_jinja_env()
        template = env.get_template(file_name)
        return template.render(context)

    def delete_params(self):
        """
        生成节点管理删除配置的参数
        """
        return [self._instance_id]

    def main(self, operator="push"):
        """
        主函数，根据操作生成对应参数
        """
        if operator == "push":
            return self.push_params()

        return self.delete_params()
