# -- coding: utf-8 --
# @File: base.py
# @Time: 2025/11/13 14:16
# @Author: windyzhao
import os
from abc import abstractmethod, ABCMeta

from django.conf import settings
from jinja2 import Environment, FileSystemLoader, DebugUndefined
from apps.core.logger import cmdb_logger as logger


class BaseNodeParams(metaclass=ABCMeta):
    PLUGIN_MAP = {}  # 插件名称映射
    plugin_name = None
    _registry = {}  # 自动收集支持的 model_id 对应的子类
    interval = 300  # 默认的采集间隔时间（秒）

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        plugin_name = getattr(cls, "plugin_name", None)
        model_id = getattr(cls, "supported_model_id", None)
        if model_id and plugin_name:
            BaseNodeParams._registry[model_id] = cls
            BaseNodeParams.PLUGIN_MAP.update({model_id: plugin_name})
        else:
            logger.warning(
                f"子类 {cls.__name__} 未正确设置 'supported_model_id' 或 'plugin_name' 属性，将不会被注册到 BaseNodeParams 中。"
            )

    def __init__(self, instance):
        self.instance = instance
        self.model_id = instance.model_id  # 当出现多对象采集的时候这个model_id就不能准确的标识唯一的model_id
        self.credential = self.instance.decrypt_credentials or {}
        self.base_path = "${STARGAZER_URL}/api/collect/collect_info"
        # 只有当子类没有定义 host_field 类属性时才设置默认值,避免覆盖子类定义
        if not hasattr(self.__class__, 'host_field'):
            self.host_field = "ip_addr"  # 默认的 ip字段 若不一样重新定义
        self.timeout = instance.timeout
        self.response_timeout = 10
        self.executor_type = "protocol"  # 默认执行器类型

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
        try:
            return self.PLUGIN_MAP[self.model_id]
        except KeyError:
            raise KeyError(f"未在 PLUGIN_MAP 中找到对应 {self.model_id} 的插件配置")

    @abstractmethod
    def set_credential(self, *args, **kwargs):
        """
        生成凭据
        TODO 后续会有多凭据 后边再改
        """
        raise NotImplementedError

    def env_config(self, *args, **kwargs):
        """
        生成环境变量配置
        """
        raise NotImplementedError

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
            }
        )
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
            "interval": self.interval,
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

    @staticmethod
    def to_toml_dict(d):
        if not d:
            return "{}"
        return "{ " + ", ".join(f'"{k}" = "{v}"' for k, v in d.items()) + " }"

    def render_template(self, context: dict):
        """
        渲染指定目录下的 j2 模板文件。
        :param context: 用于模板渲染的变量字典
        :return: 渲染后的配置字符串
        """
        file_name = "base.child.toml.j2"
        template_dir = os.path.join(settings.BASE_DIR, "apps/cmdb/support-files")
        env = Environment(loader=FileSystemLoader(template_dir), undefined=DebugUndefined)
        env.filters['to_toml'] = self.to_toml_dict
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
