# 模型分类标签
import os

from enum import Enum
from apps.cmdb.utils.time_util import parse_cmdb_time


class BaseEnum(str, Enum):
    """
    枚举基类
    """

    def __new__(cls, value, chinese):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.chinese = chinese
        return obj

    def __str__(self):
        return self.chinese

    def __repr__(self):
        return self.chinese

    @classmethod
    def get_value_choices(cls):
        """获取枚举值列表"""
        return [(item.value, item.value) for item in cls]

    @classmethod
    def get_chinese_by_value(cls, value):
        """根据value获取中文描述"""
        for item in cls:
            if item.value == value:
                return item.chinese
        return None


CLASSIFICATION = "classification"

# 模型标签
MODEL = "model"

# 实例标签
INSTANCE = "instance"

# 模型关联标签
MODEL_ASSOCIATION = "model_association"

# 实例关联标签
INSTANCE_ASSOCIATION = "instance_association"

# 拓扑主题：模型 -> 可用主题。network 主题表示「网络拓扑」视图
TOPO_THEME_NETWORK = "network"
TOPO_THEME_IPAM = "ipam"
TOPO_THEME_APP_OVERVIEW = "app_overview"
# 网络设备判定：存在 interface --belong--> <model> 的模型关联即视为网络设备
NETWORK_INTERFACE_MODEL = "interface"
NETWORK_INTERFACE_BELONG_ASST = "belong"
# 网络拓扑展开策略：默认展开 2 跳，最多 4 跳，节点上限 100（超出截断并提示，不静默丢弃）
NETWORK_TOPO_DEFAULT_HOP = 2
NETWORK_TOPO_MAX_HOP = 4
NETWORK_TOPO_NODE_LIMIT = 100


class ModelConstraintKey(BaseEnum):
    """模型约束键"""

    unique = ("is_only", "唯一键")
    required = ("is_required", "必填项")
    editable = ("editable", "可编辑")


# 模型间的关联类型
ASSOCIATION_TYPE = [
    {"asst_id": "belong", "asst_name": "属于", "is_pre": True},
    {"asst_id": "group", "asst_name": "组成", "is_pre": True},
    {"asst_id": "run", "asst_name": "运行于", "is_pre": True},
    {"asst_id": "install_on", "asst_name": "安装于", "is_pre": True},
    {"asst_id": "contains", "asst_name": "包含", "is_pre": True},
    {"asst_id": "connect", "asst_name": "关联", "is_pre": True},
]

# 需要进行ID与NAME转化的属性类型
ENUM = "enum"
USER = "user"
ORGANIZATION = "organization"

ENUM_SELECT_MODE_SINGLE = "single"
ENUM_SELECT_MODE_MULTIPLE = "multiple"
ENUM_SELECT_MODE_CHOICES = (ENUM_SELECT_MODE_SINGLE, ENUM_SELECT_MODE_MULTIPLE)
ENUM_SELECT_MODE_DEFAULT = ENUM_SELECT_MODE_SINGLE

# 模型内置属性：组织
INIT_MODEL_GROUP = "group"

# 默认的实例名属性
INST_NAME_INFOS = [
    {
        "attr_id": "inst_name",
        "attr_name": "实例名",
        "attr_type": "str",
        "is_only": True,
        "is_required": True,
        "editable": True,
        "option": {},
        "attr_group": "default",
        "user_prompt": "用于区分不同实例的唯一名称",
        "is_pre": True,
    },
    {
        "attr_id": ORGANIZATION,
        "attr_name": "所属组织",
        "attr_type": ORGANIZATION,
        "is_only": False,
        "is_required": True,
        "editable": True,
        "option": [],
        "attr_group": "default",
        "is_pre": True,
        "user_prompt": "实例所属的组织",
    },
]

# 创建模型分类时校验属性
CREATE_CLASSIFICATION_CHECK_ATTR_MAP = dict(
    is_only={"classification_id": "模型分类ID", "classification_name": "模型分类名称"},
    is_required={
        "classification_id": "模型分类ID",
        "classification_name": "模型分类名称",
    },
)
# 更新模型分类时校验属性
UPDATE_CLASSIFICATION_check_attr_map = dict(
    is_only={"classification_name": "模型分类名称"},
    is_required={"classification_name": "模型分类名称"},
    editable={"classification_name": "模型分类名称"},
)
# 创建模型时校验属性
CREATE_MODEL_CHECK_ATTR = dict(
    is_only={"model_id": "模型ID", "model_name": "模型名称"},
    is_required={"model_id": "模型ID", "model_name": "模型名称"},
)
# 更新模型时校验属性
UPDATE_MODEL_CHECK_ATTR_MAP = dict(
    is_only={"model_name": "模型名称"},
    is_required={"model_name": "模型名称"},
    editable={
        "model_name": "模型名称",
        "classification_id": "模型分类ID",
        "icn": "图标",
        "group": "组织",
    },
)

# 需要进行类型转换的数据类型
NEED_CONVERSION_TYPE = {
    "bool": lambda x: True if x in {"true", "True", "TRUE", True} else False,
    "int": int,
    "float": float,
    "str": str,
    "list": list,
    "time": parse_cmdb_time,
}

EDGE_TYPE = 2
ENTITY_TYPE = 1

# 凭据标签
CREDENTIAL = "credential"

# 凭据实例关联标签
CREDENTIAL_ASSOCIATION = "credential_association"

# 模型分类与模型关联
SUBORDINATE_MODEL = "subordinate_model"

# 加密的属性列表
ENCRYPTED_KEY = {"password", "secret_key", "encryption_key"}

ATTR_TYPE_MAP = {
    "str": "字符串",
    "int": "整数",
    "enum": "枚举",
    "tag": "标签",
    "time": "时间",
    "user": " 用户",
    "pwd": "密码",
    "bool": "布尔",
    "organization": "组织",
    "table": "表格",
}

# ===================

OPERATOR_INSTANCE = "资产实例"
OPERATOR_MODEL = "模型管理"
OPERATOR_COLLECT_TASK = "采集任务"

# ====== Display Field 配置 ======
# _display 字段的属性配置
DISPLAY_FIELD_CONFIG = {
    "attr_type": "str",  # 冗余字段统一为字符串类型
    "editable": True,
    "is_only": False,  # 不需要唯一性校验
    "is_required": False,  # 非必填
    "is_display_field": True,  # 标记为冗余展示字段，前端不展示此字段
}


# ====== 配置采集 ======


class CollectRunStatusType(object):
    NOT_START = 0
    RUNNING = 1
    SUCCESS = 2
    ERROR = 3
    TIME_OUT = 4
    WRITING = 5
    FORCE_STOP = 6
    PARTIAL_SUCCESS = 8

    CHOICE = (
        (NOT_START, "未执行"),
        (RUNNING, "正在采集"),
        (SUCCESS, "成功"),
        (ERROR, "异常"),
        (TIME_OUT, "超时"),
        (WRITING, "正在写入"),
        (FORCE_STOP, "强制终止"),
        (PARTIAL_SUCCESS, "部分成功"),
    )


class CollectPluginTypes(object):
    """
    采集插件类型
    """

    VM = "vm"
    SNMP = "snmp"
    K8S = "k8s"
    CLOUD = "cloud"
    PROTOCOL = "protocol"
    HOST = "host"
    DB = "db"
    MIDDLEWARE = "middleware"
    CONFIG_FILE = "config_file"
    IP = "ip"
    OTHER = "other"

    CHOICE = (
        (VM, "VM采集"),
        (SNMP, "SNMP采集"),
        (K8S, "K8S采集"),
        (CLOUD, "云采集"),
        (PROTOCOL, "协议采集"),
        (HOST, "主机采集"),
        (DB, "数据库采集"),
        (MIDDLEWARE, "中间件采集"),
        (CONFIG_FILE, "配置文件采集"),
        (IP, "IP采集"),
        (OTHER, "其他采集"),
    )


class CollectInputMethod(object):
    """
    采集录入方式
    """

    AUTO = 0
    MANUAL = 1
    SUBNET = 2  # 选子网：IP 发现任务专属录入方式（§13）

    CHOICE = (
        (AUTO, "自动"),
        (MANUAL, "手动"),
        (SUBNET, "选子网"),
    )


class DataCleanupStrategy(object):
    """
    数据清理策略
    """

    NO_CLEANUP = "no_cleanup"  # 不清理（默认）
    IMMEDIATELY = "immediately"  # 及时清理：采集同步时立即删除不存在的实例
    AFTER_EXPIRATION = "after_expiration"  # 过期删除：定时任务检查过期实例并删除

    CHOICE = (
        (NO_CLEANUP, "不清理"),
        (IMMEDIATELY, "及时清理"),
        (AFTER_EXPIRATION, "过期删除"),
    )

    DEFAULT = NO_CLEANUP


class CollectDriverTypes(object):
    """
    采集驱动类型
    """

    PROTOCOL = "protocol"
    JOB = "job"

    CHOICE = ((PROTOCOL, "协议采集"), (JOB, "脚本采集"))


# 采集对象树基线骨架
"""
encrypted_fields: 需要加密的字段列表。

当前 COLLECT_OBJ_TREE 作为社区版对象树基线骨架使用。
运行时对象树会在此基础上，叠加 enterprise 中定义的额外 children。
"""
COLLECT_OBJ_TREE = [
    {
        "id": "k8s",
        "name": "容器",
        "children": [
            {
                "id": "k8s_cluster",
                "model_id": "k8s_cluster",
                "name": "K8S",
                "task_type": CollectPluginTypes.K8S,
                "type": CollectDriverTypes.PROTOCOL,
                "tag": ["apiserver"],
                "desc": "采集k8s集群核心对象node节点、命名空间、工作负载、pod",
                "encrypted_fields": [],
            },
            {
                "id": "docker",
                "model_id": "docker",
                "name": "Docker",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux"],
                "desc": "发现与采集Docker容器配置信息",
                "encrypted_fields": ["password"],
            },
        ],
    },
    {
        "id": "vmware",
        "name": "虚拟化",
        "children": [
            {
                "id": "vmware_vc",
                "model_id": "vmware_vc",
                "name": "vCenter",
                "task_type": CollectPluginTypes.VM,
                "type": CollectDriverTypes.PROTOCOL,
                "tag": ["vSphere API", "SDK"],
                "desc": "通过采集vCenter内ESXi与虚拟机清单及其属性信息",
                "encrypted_fields": ["password"],
            }
        ],
    },
    {
        "id": "network",
        "name": "NetWork",
        "children": [
            {
                "id": "network",
                "model_id": "network",
                "name": "NetWork",
                "task_type": CollectPluginTypes.SNMP,
                "type": CollectDriverTypes.PROTOCOL,
                "tag": ["SNMP", "Interfaces"],
                "desc": "通过SNMP协议发现网络设备和网络拓扑及其基本信息",
                "encrypted_fields": ["authkey", "privkey", "community"],
            }
        ],
    },
    {
        "id": "databases",
        "name": "数据库",
        "children": [
            {
                "id": "mysql",
                "model_id": "mysql",
                "name": "Mysql",
                "task_type": CollectPluginTypes.PROTOCOL,
                "type": CollectDriverTypes.PROTOCOL,
                "tag": ["Agentless", "TCP"],
                "desc": "采集MySQL关键配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "influxdb",
                "model_id": "influxdb",
                "name": "【BETA】InfluxDB",
                "task_type": CollectPluginTypes.PROTOCOL,
                "type": CollectDriverTypes.PROTOCOL,
                "tag": ["Agentless", "HTTP", "Beta"],
                "desc": "采集InfluxDB关键配置信息（兼容1.x/2.x，优先2.x）",
                "encrypted_fields": ["password", "token"],
            },
            {
                "id": "postgresql",
                "model_id": "postgresql",
                "name": "PostgreSQL",
                "task_type": CollectPluginTypes.PROTOCOL,
                "type": CollectDriverTypes.PROTOCOL,
                "tag": ["Agentless", "TCP"],
                "desc": "采集PostgreSQL关键配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "mssql",
                "model_id": "mssql",
                "name": "【BETA】MSSQL",
                "task_type": CollectPluginTypes.PROTOCOL,
                "type": CollectDriverTypes.PROTOCOL,
                "tag": ["Agentless", "TCP", "Windows", "SQL Server"],
                "desc": "采集MSSQL关键配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "redis",
                "model_id": "redis",
                "name": "Redis",
                "task_type": CollectPluginTypes.DB,
                "type": CollectDriverTypes.JOB,
                "tag": ["Agent", "JOB", "Linux"],
                "desc": "采集Redis关键配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "mongodb",
                "model_id": "mongodb",
                "name": "【BETA】MongoDB",
                "task_type": CollectPluginTypes.DB,
                "type": CollectDriverTypes.JOB,
                "tag": ["Agent", "JOB", "Linux"],
                "desc": "发现与采集MongoDB基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "es",
                "model_id": "es",
                "name": "【BETA】Elasticsearch",
                "task_type": CollectPluginTypes.DB,
                "type": CollectDriverTypes.JOB,
                "tag": ["Agent", "JOB", "Linux"],
                "desc": "采集Elasticsearch关键配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "hbase",
                "model_id": "hbase",
                "name": "【BETA】HBase",
                "task_type": CollectPluginTypes.DB,
                "type": CollectDriverTypes.JOB,
                "tag": ["Agent", "JOB", "Linux"],
                "desc": "采集HBase关键配置信息",
                "encrypted_fields": ["password"],
            },
        ],
    },
    {
        "id": "storage_device",
        "name": "存储设备",
        "children": [
            {
                "id": "storage",
                "model_id": "storage",
                "name": "【BETA】华为存储",
                "task_type": CollectPluginTypes.CLOUD,
                "type": CollectDriverTypes.PROTOCOL,
                "tag": ["Agentless", "HTTPS", "Beta"],
                "desc": "采集华为 OceanStor 存储设备及其存储池、磁盘、卷（LUN）",
                "encrypted_fields": ["password"],
            },
        ],
    },
    {
        "id": "cloud",
        "name": "云平台",
        "children": [
            {
                "id": "aliyun_account",
                "model_id": "aliyun_account",
                "name": "阿里云",
                "task_type": CollectPluginTypes.CLOUD,
                "type": CollectDriverTypes.PROTOCOL,
                "tag": ["SDK"],
                "desc": "采集阿里云账户下ECS、VPC、RDS等资产清单",
                "encrypted_fields": ["accessKey", "accessSecret"],
            },
            {
                "id": "qcloud",
                "model_id": "qcloud",
                "name": "腾讯云",
                "task_type": CollectPluginTypes.CLOUD,
                "type": CollectDriverTypes.PROTOCOL,
                "tag": ["SDK"],
                "desc": "采集腾讯云账户下CVM、VPC、云数据库等资产清单",
                "encrypted_fields": ["accessKey", "accessSecret"],
            },
            {
                "id": "hwcloud",
                "model_id": "hwcloud",
                "name": "华为云【beta】",
                "task_type": CollectPluginTypes.CLOUD,
                "type": CollectDriverTypes.PROTOCOL,
                "tag": ["SDK"],
                "desc": "采集华为云平台及其下 ECS 等资产清单",
                "encrypted_fields": ["accessKey", "accessSecret"],
            },
            {
                "id": "fusioninsight",
                "model_id": "fusioninsight",
                "name": "FusionInsight【beta】",
                "task_type": CollectPluginTypes.CLOUD,
                "type": CollectDriverTypes.PROTOCOL,
                "tag": ["SDK"],
                "desc": "采集 FusionInsight 平台及其下集群、主机",
                "encrypted_fields": ["accessKey", "accessSecret"],
            },
        ],
    },
    {
        "id": "host_manage",
        "name": "主机管理",
        "children": [
            {
                "id": "host",
                "model_id": "host",
                "name": "主机",
                "task_type": CollectPluginTypes.HOST,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux"],
                "desc": "采集操作系统基础信息CPU内存等",
                "encrypted_fields": ["password"],
            },
            {
                "id": "config_file",
                "model_id": "config_file",
                "target_model_id": "host",
                "name": "配置文件",
                "task_type": CollectPluginTypes.CONFIG_FILE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux", "Windows"],
                "desc": "采集主机操作系统层文本配置文件内容",
                "encrypted_fields": ["password"],
            },
            {
                "id": "physcial_server",
                "model_id": "physcial_server",
                "name": "物理服务器 SSH",
                "task_type": CollectPluginTypes.HOST,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux"],
                "desc": "采集物理服务器基础信息CPU、内存、网卡等",
                "encrypted_fields": ["password"],
            },
            {
                "id": "physcial_server_ipmi",
                "model_id": "physcial_server",
                "name": "【BETA】物理服务器 IPMI",
                "task_type": CollectPluginTypes.PROTOCOL,
                "type": CollectDriverTypes.PROTOCOL,
                "tag": ["IPMI", "BMC"],
                "desc": "通过 IPMI 管理口采集物理服务器基础身份信息",
                "encrypted_fields": ["password"],
            },
        ],
    },
    {
        "id": "middleware",
        "name": "中间件",
        "children": [
            {
                "id": "nginx",
                "model_id": "nginx",
                "name": "Nginx",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux"],
                "desc": "发现与采集Nginx基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "minio",
                "model_id": "minio",
                "name": "【BETA】MinIO",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux", "Beta"],
                "desc": "发现与采集MinIO对象存储的基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "zookeeper",
                "model_id": "zookeeper",
                "name": "Zookeeper",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux"],
                "desc": "发现与采集ZK基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "kafka",
                "model_id": "kafka",
                "name": "Kafka",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux"],
                "desc": "发现与采集Kafka基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "consul",
                "model_id": "consul",
                "name": "Consul",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux"],
                "desc": "发现与采集Consul基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "etcd",
                "model_id": "etcd",
                "name": "Etcd",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux"],
                "desc": "发现与采集Etcd基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "rabbitmq",
                "model_id": "rabbitmq",
                "name": "RabbitMQ",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux"],
                "desc": "发现与采集Rabbitmq基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "tomcat",
                "model_id": "tomcat",
                "name": "Tomcat",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux"],
                "desc": "发现与采集Tomcat基础配置信息",
                "encrypted_fields": ["password"],
            },
            # 以下为未测试通过的对象
            {
                "id": "apache",
                "model_id": "apache",
                "name": "Apache",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux", "Beta"],
                "desc": "发现与采集Apache基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "activemq",
                "model_id": "activemq",
                "name": "ActiveMQ",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux", "Beta"],
                "desc": "发现与采集ActiveMQ基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "iis",
                "model_id": "iis",
                "name": "IIS",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Windows", "Beta"],
                "desc": "发现与采集IIS基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "tuxedo",
                "model_id": "tuxedo",
                "name": "Tuxedo",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux", "Beta"],
                "desc": "发现与采集Tuxedo基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "memcached",
                "model_id": "memcached",
                "name": "Memcached",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux", "Beta"],
                "desc": "发现与采集Memcached基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "rocketmq",
                "model_id": "rocketmq",
                "name": "RocketMQ",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux", "Beta"],
                "desc": "发现与采集RocketMQ基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "openresty",
                "model_id": "openresty",
                "name": "OpenResty",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux", "Beta"],
                "desc": "发现与采集OpenResty基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "squid",
                "model_id": "squid",
                "name": "Squid",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux", "Beta"],
                "desc": "发现与采集Squid基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "haproxy",
                "model_id": "haproxy",
                "name": "HAProxy",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux", "Beta"],
                "desc": "发现与采集HAProxy基础配置信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "keepalive",
                "model_id": "keepalive",
                "name": "KeepAlive【beta】",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux", "Beta"],
                "desc": "采集 KeepAlive 实例的 IP、端口、版本、优先级、状态、虚拟路由 ID 等信息",
                "encrypted_fields": ["password"],
            },
            {
                "id": "spark",
                "model_id": "spark",
                "name": "Spark",
                "task_type": CollectPluginTypes.MIDDLEWARE,
                "type": CollectDriverTypes.JOB,
                "tag": ["JOB", "Linux", "Beta"],
                "desc": "发现与采集Spark基础配置信息",
                "encrypted_fields": ["password"],
            },
        ],
    },
]

# ====== 配置采集 ======

VICTORIAMETRICS_HOST = os.getenv("VICTORIAMETRICS_HOST", "")

STARGAZER_URL = os.getenv("STARGAZER_URL", "http://stargazer:8083")
# ===== 实例权限 =====
PERMISSION_INSTANCES = "instances"  # 实例
PERMISSION_TASK = "task"  # 采集任务
PERMISSION_MODEL = "model"  # 模型
OPERATE = "Operate"
VIEW = "View"
APP_NAME = "cmdb"

# ===========
# BL-NEW-006：移除源码内置的固定加密密钥（源码/库泄露后可被用于解密凭据）。
# 与 Django 主 SECRET_KEY（config/components/base.py）一致，仅从环境变量读取；
# 未配置时为空串，凭据加解密会显式失败，而非静默使用已知的硬编码密钥。
SECRET_KEY = os.getenv("SECRET_KEY", "")
