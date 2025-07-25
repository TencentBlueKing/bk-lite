# -- coding: utf-8 --
# @File: node_configs.py
# @Time: 2025/3/21 14:19
# @Author: windyzhao
import ipaddress
from abc import abstractmethod, ABCMeta

from jinja2 import Environment, FileSystemLoader, DebugUndefined


class BaseNodeParams(metaclass=ABCMeta):
    PLUGIN_MAP = {}  # 插件名称映射
    plugin_name = None
    _registry = {}  # 自动收集支持的 model_id 对应的子类
    BASE_INTERVAL_MAP = {"vmware_vc": 300, "network": 300, "network_topo": 300, "mysql_info": 300,
                         "aliyun_account": 300, "qcloud": 300, }  # 默认的采集间隔时间

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
        interval_map = getattr(cls, "interval_map", None)
        if interval_map:
            BaseNodeParams.BASE_INTERVAL_MAP.update(interval_map)

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
                "interval": self.BASE_INTERVAL_MAP.get(self.model_id, 300),
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
        template_dir = "apps/cmdb/plugins/Telegraf/http/"
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
        else:
            return self.delete_params()


class VmwareNodeParams(BaseNodeParams):
    supported_model_id = "vmware_vc"  # 通过此属性自动注册
    plugin_name = "vmware_info"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 当 instance.model_id 为 "network" 时，PLUGIN_MAP 配置为 "snmp_facts"
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "hostname"

    def set_credential(self, *args, **kwargs):
        """
        生成 vmware vc 的凭据
        """
        credential_data = {
            "username": self.credential.get("username"),
            "password": self.credential.get("password"),
            "port": self.credential.get("port", 443),
            "ssl": str(self.credential.get("ssl", False)).lower(),
        }
        return credential_data

    def get_instance_id(self, instance):
        """
        获取实例 id
        """
        return f"{self.instance.id}_{instance['inst_name']}"


class NetworkNodeParams(BaseNodeParams):
    supported_model_id = "network"  # 通过此属性自动注册
    plugin_name = "snmp_facts"  # 插件名称

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 当 instance.model_id 为 "vmware_vc" 时，PLUGIN_MAP 配置为 "vmware_info"
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "ip_addr"

    def set_credential(self, *args, **kwargs):
        """
        生成 network 的凭据
        # 示例参数：
        # {
        #     "host": "10.10.69.246",
        #     "version": "v3",
        #     "username": "weops",
        #     "level": "authPriv",
        #     "integrity": "sha",
        #     "privacy": "aes",
        #     "authkey": "WeOps@2024",
        #     "privkey": "1145141919",
        #     "timeout": 5,
        #     "retries": 3,
        #     "snmp_port": 161,
        #     "community": "",
        # }
        """

        credential_data = {
            "snmp_port": self.credential.get("snmp_port", 161),
            "community": self.credential.get("community", ""),
            "version": self.credential.get("version", ""),
            "username": self.credential.get("username", ""),
            "level": self.credential.get("level", ""),
            "integrity": self.credential.get("integrity", ""),
            "privacy": self.credential.get("privacy", ""),
            "authkey": self.credential.get("authkey", ""),
            "privkey": self.credential.get("privkey", ""),
            "timeout": self.credential.get("timeout", "1"),
        }
        if self.model_id == "network_topo":
            credential_data.update({"topo": "true"})
        return credential_data

    def get_instance_id(self, instance):
        """
        获取实例 id
        """
        if self.has_set_instances:
            return f"{self.instance.id}_{instance['inst_name']}"
        else:
            return f"{self.instance.id}_{instance}"


class MysqlNodeParams(BaseNodeParams):
    supported_model_id = "mysql"  # 通过此属性自动注册
    plugin_name = "mysql_info"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 当 instance.model_id 为 "vmware_vc" 时，PLUGIN_MAP 配置为 "vmware_info"
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "ip_addr"

    def set_credential(self, *args, **kwargs):
        credential_data = {
            "port": self.credential.get("port", 3306),
            "user": self.credential.get("user", ""),
            "password": self.credential.get("password", ""),
        }
        return credential_data

    def get_instance_id(self, instance):
        """
        获取实例 id
        """
        if self.has_set_instances:
            return f"{self.instance.id}_{instance['inst_name']}"
        else:
            return f"{self.instance.id}_{instance}"


class AliyunNodeParams(BaseNodeParams):
    supported_model_id = "aliyun_account"
    plugin_name = "aliyun_info"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})

    def set_credential(self, *args, **kwargs):
        regions_id = self.credential["regions"]["resource_id"]
        credential_data = {
            "access_key": self.credential.get("accessKey", ""),
            "access_secret": self.credential.get("accessSecret", ""),
            "region_id": regions_id
        }
        return credential_data

    def get_instance_id(self, instance):
        """
        获取实例 id
        """
        if self.has_set_instances:
            return f"{self.instance.id}_{instance['inst_name']}"
        else:
            return f"{self.instance.id}_{instance}"


class SSHNodeParamsMixin:
    supported_model_id = ""
    plugin_name = f"{supported_model_id}_info"
    interval_map = {plugin_name: 300}
    host_field = "ip_addr"

    def set_credential(self, *args, **kwargs):
        host = kwargs["host"]
        node_ip = self.instance.access_point[0]["ip"]
        credential_data = {
            "node_id": self.instance.access_point[0]["id"],
            "execute_timeout": self.instance.timeout,
        }
        host_ip = host.get("ip_addr", "") if host and isinstance(host, dict) else host
        if host_ip != node_ip:
            credential_data["username"] = self.credential.get("username", ""),
            credential_data["password"] = self.credential.get("password", ""),
            credential_data["port"] = self.credential.get("port", 22),
        return credential_data

    def get_instance_id(self, instance):
        return f"{self.instance.id}_{instance}_{instance['inst_name']}" if self.has_set_instances else f"{self.instance.id}_{instance}"


class HostNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "host"  # 模型id
    plugin_name = "host_info"  # 插件名称


class RedisNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "redis"
    plugin_name = "redis_info"


class NginxNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "nginx"
    plugin_name = "nginx_info"


class ZookeeperNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "zookeeper"
    plugin_name = "zookeeper_info"


class KafkaNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "kafka"
    plugin_name = "kafka_info"


class QCloudNodeParams(BaseNodeParams):
    supported_model_id = "qcloud"
    plugin_name = "qcloud_info"

    interval_map = {plugin_name: 300}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: "qcloud_info"})

    def set_credential(self, *args, **kwargs):
        """
        生成 Tencent Cloud 的凭据
        """
        return {
            "secret_id": self.credential.get("accessKey", ""),
            "secret_key": self.credential.get("secretSecret", ""),
        }

    def get_instance_id(self, instance):
        """
        获取实例 ID
        """
        return f"{self.instance.id}_{instance['inst_name']}"


class EtcdNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "etcd"
    plugin_name = "etcd_info"


class RabbitMQNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "rabbitmq"
    plugin_name = "rabbitmq_info"


class TomcatNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "tomcat"
    plugin_name = "tomcat_info"


class ESNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "es"
    plugin_name = "es_info"


class MongoDBParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "mongodb"
    plugin_name = "mongodb_info"


class ApacheNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "apache"
    plugin_name = "apache_info"


class ActiveMQNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "activemq"
    plugin_name = "activemq_info"


class PgsqlNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "postgresql"
    plugin_name = "pgsql_info"


class WeblogicNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "weblogic"
    plugin_name = "weblogic_info"


class KeepalivedNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "weblogic"
    plugin_name = "weblogic_info"


class NodeParamsFactory:
    """
    工厂类，根据 instance 的 model_id 返回对应的 NodeParams 实例
    """

    @staticmethod
    def get_node_params(instance):
        params_cls = BaseNodeParams._registry.get(instance.model_id)
        if params_cls is None:
            raise ValueError(f"不支持的 model_id: {instance.model_id}")
        return params_cls(instance)
