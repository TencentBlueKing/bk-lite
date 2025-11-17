# -- coding: utf-8 --
# @File: base.py
# @Time: 2025/11/13 14:16
# @Author: windyzhao

import ipaddress
from abc import abstractmethod, ABCMeta

from jinja2 import Environment, FileSystemLoader, DebugUndefined


class BaseNodeParams(metaclass=ABCMeta):
    PLUGIN_MAP = {}  # 插件名称映射
    plugin_name = None
    _registry = {}  # 自动收集支持的 model_id 对应的子类
    interval = 300  # 默认的采集间隔时间（秒）

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        model_id = getattr(cls, "supported_model_id", None)
        if model_id:
            BaseNodeParams._registry[model_id] = cls
            if model_id == "network":
                BaseNodeParams._registry["network_topo"] = cls
            plugin_name = getattr(cls, "plugin_name", None)
            if plugin_name:
                BaseNodeParams.PLUGIN_MAP.update({model_id: plugin_name})

    def __init__(self, instance):
        self.instance = instance
        self.model_id = instance.model_id
        self.credential = self.instance.credential
        self.base_path = "${STARGAZER_URL}/api/collect/collect_info"
        self.host_field = "host"  # 默认的 ip字段 若不一样重新定义
        self.timeout = 40 if self.instance.is_cloud else 30
        self.response_timeout = 40 if self.instance.is_cloud else 30

    def get_host_ip_addr(self, host):
        if isinstance(host, dict):
            ip_addr = host.get(self.host_field, "")
        else:
            ip_addr = host
        return "host", ip_addr

    @property
    def has_set_instances(self):
        return bool(self.instance.instances)

    @property
    def has_set_ip_range(self):
        return bool(self.instance.ip_range)

    @staticmethod
    def expand_ip_range(ip_range: str) -> list:
        """
        将类似 '192.168.0.1-192.168.0.10' 的网段拆分成单个 IP 地址列表
        """
        try:
            start_str, end_str = ip_range.split('-')
            start_ip = ipaddress.IPv4Address(start_str.strip())
            end_ip = ipaddress.IPv4Address(end_str.strip())
        except Exception as e:
            raise ValueError(f"无效的 IP 网段格式: {ip_range}") from e

        if start_ip > end_ip:
            raise ValueError("起始 IP 不能大于结束 IP")

        ips = [str(ipaddress.IPv4Address(ip)) for ip in range(int(start_ip), int(end_ip) + 1)]
        return ips

    @property
    def hosts(self):
        """
        获取实例列表
        如果没有选择实例 则 是配置了 ip_range
        """
        return self.instance.instances or self.expand_ip_range(self.instance.ip_range)

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
        """
        raise NotImplementedError

    def custom_headers(self, host):
        """
        格式化服务器的路径
        """
        _key, _value = self.get_host_ip_addr(host)
        params = self.set_credential(host=host)
        params.update({"plugin_name": self.model_plugin_name, _key: _value})
        _params = {f"cmdb{k}": str(v) for k, v in params.items()}
        return _params

    @property
    def get_instance_type(self):
        if self.model_id == "vmware_vc":
            instance_type = "vmware"
        else:
            instance_type = self.model_id
        return f"cmdb_{instance_type}"

    @abstractmethod
    def get_instance_id(self, instance):
        """
        获取实例 id，如果没有特殊处理的话就是使用默认配置
        """
        raise NotImplementedError

    def push_params(self):
        """
        生成节点管理创建配置的参数
        """
        if self.plugin_name is None:
            raise ValueError("插件名称未设置，请检查 plugin_name 是否正确")

        node = self.instance.access_point[0]
        nodes = []
        for host in self.hosts:
            content = {
                "instance_id": str(self.get_instance_id(host)),
                "interval": self.interval,
                "instance_type": self.get_instance_type,
                "timeout": self.timeout,
                "response_timeout": self.response_timeout,
                "headers": self.custom_headers(host=host),
                "config_type": self.model_id
            }
            jinja_context = self.render_template(context=content)
            nodes.append({
                "id": self.get_instance_id(host),
                "collect_type": "http",
                "type": self.model_id,
                "content": jinja_context,
                "node_id": node["id"],
                "collector_name": "Telegraf",
                "env_config": {}
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
        template_dir = "/apps/cmdb/support-files"
        env = Environment(loader=FileSystemLoader(template_dir), undefined=DebugUndefined)
        env.filters['to_toml'] = self.to_toml_dict
        template = env.get_template(file_name)
        return template.render(context)

    def delete_params(self):
        """
        生成节点管理删除配置的参数
        """
        return [str(self.get_instance_id(host)) for host in self.hosts]

    def main(self, operator="push"):
        """
        主函数，根据操作生成对应参数
        """
        if operator == "push":
            return self.push_params()

        return self.delete_params()
