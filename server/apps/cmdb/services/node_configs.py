# -- coding: utf-8 --
# @File: node_configs.py
# @Time: 2025/3/21 14:19
# @Author: windyzhao
import copy
import ipaddress
import urllib.parse
from abc import abstractmethod, ABCMeta


class BaseNodeParams(metaclass=ABCMeta):
    PLUGIN_MAP = {}
    _registry = {}  # 自动收集支持的 model_id 对应的子类
    BASE_INTERVAL_MAP = {"vmware_vc": 300, "network": 300, "network_topo": 300, "mysql_info": 300}  # 默认的采集间隔时间

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        model_id = getattr(cls, "supported_model_id", None)
        if model_id:
            BaseNodeParams._registry[model_id] = cls
            if model_id == "network":
                BaseNodeParams._registry["network_topo"] = cls

    def __init__(self, instance):
        self.instance = instance
        self.model_id = instance.model_id
        self.credential = self.instance.credential
        self.base_path = "${STARGAZER_URL}/api/collect/collect_info"
        self.host_field = "host"  # 默认的 ip字段 若不一样重新定义

    def get_host_ip_addr(self, host):
        if isinstance(host, dict):
            ip_addr = host["ip_addr"]
        else:
            ip_addr = host
        return self.host_field, ip_addr

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
    def set_credential(self):
        """
        生成凭据
        """
        raise NotImplementedError

    @property
    def format_server_path(self):
        """
        格式化服务器的路径
        """
        params = self.set_credential()
        params.update({"plugin_name": self.model_plugin_name})
        encoded_params = {k: urllib.parse.quote(str(v), safe='@') for k, v in params.items()}
        url = f"{self.base_path}?" + "&".join(f"{k}={v}" for k, v in encoded_params.items())
        return url

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
        url = self.format_server_path
        node = self.instance.access_point[0]
        nodes = []
        for host in self.hosts:
            _url = copy.deepcopy(url)
            _key, _value = self.get_host_ip_addr(host)
            _url += "&{}={}".format(_key, _value)
            nodes.append({
                "id": node["id"],
                "configs": [{
                    "url": _url,
                    "type": "http",
                    "instance_id": str((self.get_instance_id(host),)),
                    "interval": self.BASE_INTERVAL_MAP.get(self.model_id, 60),
                    "instance_type": self.get_instance_type
                    # "task_id": self.instance.id,
                }]
            })
        return {"object_type": "http", "nodes": nodes}

    def delete_params(self):
        """
        生成节点管理删除配置的参数
        """
        return [str((self.get_instance_id(host),)) for host in self.hosts]

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 当 instance.model_id 为 "network" 时，PLUGIN_MAP 配置为 "snmp_facts"
        self.PLUGIN_MAP.update({self.model_id: "vmware_info"})
        self.host_field = "hostname"

    def set_credential(self):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 当 instance.model_id 为 "vmware_vc" 时，PLUGIN_MAP 配置为 "vmware_info"
        self.PLUGIN_MAP.update({self.model_id: "snmp_facts"})

    def set_credential(self):
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
            "timeout": self.credential.get("timeout", ""),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 当 instance.model_id 为 "vmware_vc" 时，PLUGIN_MAP 配置为 "vmware_info"
        self.PLUGIN_MAP.update({self.model_id: "mysql_info"})

    def set_credential(self):
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
