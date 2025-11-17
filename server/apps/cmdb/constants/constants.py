# 模型分类标签
import os

from enum import Enum


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
    },
]

# 创建模型分类时校验属性
CREATE_CLASSIFICATION_CHECK_ATTR_MAP = dict(
    is_only={"classification_id": "模型分类ID", "classification_name": "模型分类名称"},
    is_required={"classification_id": "模型分类ID", "classification_name": "模型分类名称"},
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
    editable={"model_name": "模型名称", "classification_id": "模型分类ID", "icn": "图标", "group": "组织"},
)

# 需要进行类型转换的数据类型
NEED_CONVERSION_TYPE = {
    "bool": lambda x: True if x in {"true", "True", "TRUE", True} else False,
    "int": int,
    "float": float,
    "str": str,
    "list": list,
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
    "time": "时间",
    "user": " 用户",
    "pwd": "密码",
    "bool": "布尔",
    "organization": "组织"
}

# ===================

OPERATOR_INSTANCE = "资产实例"
OPERATOR_MODEL = "模型管理"
OPERATOR_COLLECT_TASK = "采集任务"


# ===================


# ====== 配置采集 ======

class CollectRunStatusType(object):
    NOT_START = 0
    RUNNING = 1
    SUCCESS = 2
    ERROR = 3
    TIME_OUT = 4
    WRITING = 5
    FORCE_STOP = 6
    EXAMINE = 7  # 审批 但是不做枚举

    CHOICE = (
        (NOT_START, "未执行"),
        (RUNNING, "正在采集"),
        (SUCCESS, "成功"),
        (ERROR, "异常"),
        (TIME_OUT, "超时"),
        (EXAMINE, "待审批"),
        (WRITING, "正在写入"),
        (FORCE_STOP, "强制终止"),
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
        (IP, "IP采集"),
        (OTHER, "其他采集"),
    )


class CollectInputMethod(object):
    """
    采集录入方式
    """

    AUTO = 0
    MANUAL = 1

    CHOICE = (
        (AUTO, "自动"),
        (MANUAL, "手动"),
    )


class CollectDriverTypes(object):
    """
    采集驱动类型
    """

    PROTOCOL = "protocol"
    JOB = "job"

    CHOICE = (
        (PROTOCOL, "协议采集"),
        (JOB, "脚本采集")
    )


# 采集对象树
COLLECT_OBJ_TREE = [
    {
        "id": "k8s",
        "name": "K8S",
        "children": [
            {"id": "k8s_cluster", "model_id": "k8s_cluster", "name": "K8S", "task_type": CollectPluginTypes.K8S,
             "type": CollectDriverTypes.PROTOCOL}
        ],
    },
    {
        "id": "vmware",
        "name": "VMware",
        "children": [
            {"id": "vmware_vc", "model_id": "vmware_vc", "name": "vCenter", "task_type": CollectPluginTypes.VM,
             "type": CollectDriverTypes.PROTOCOL}
        ],
    },
    {
        "id": "network",
        "name": "NetWork",
        "children": [
            {"id": "network", "model_id": "network", "name": "NetWork", "task_type": CollectPluginTypes.SNMP,
             "type": CollectDriverTypes.PROTOCOL}
        ],
    },
    {
        "id": "network_topo",
        "name": "网络拓扑",
        "children": [
            {"id": "network_topo", "model_id": "network_topo", "name": "网络拓扑", "task_type": CollectPluginTypes.SNMP,
             "type": CollectDriverTypes.PROTOCOL}
        ],
    },
    {
        "id": "databases",
        "name": "数据库",
        "children": [
            {"id": "mysql", "model_id": "mysql", "name": "Mysql", "task_type": CollectPluginTypes.PROTOCOL,
             "type": CollectDriverTypes.PROTOCOL},
            {
                "id": "redis",
                "model_id": "redis",
                "name": "Redis",
                "task_type": CollectPluginTypes.DB,
                "type": CollectDriverTypes.JOB,
            }
        ],
    },
    {
        "id": "cloud",
        "name": "云平台",
        "children": [
            {"id": "aliyun", "model_id": "aliyun_account", "name": "阿里云", "task_type": CollectPluginTypes.CLOUD,
             "type": CollectDriverTypes.PROTOCOL},
            {
                "id": "qcloud", "model_id": "qcloud", "name": "腾讯云", "task_type": CollectPluginTypes.CLOUD,
                "type": CollectDriverTypes.PROTOCOL
            },
        ],
    },
    {
        "id": "host_manage",
        "name": "主机管理",
        "children": [
            {"id": "host", "model_id": "host", "name": "主机", "task_type": CollectPluginTypes.HOST,
             "type": CollectDriverTypes.JOB}
        ],
    },
    {
        "id": "middleware",
        "name": "中间件",
        "children": [
            {"id": "nginx", "model_id": "nginx", "name": "Nginx", "task_type": CollectPluginTypes.MIDDLEWARE,
             "type": CollectDriverTypes.JOB},
            {"id": "zookeeper", "model_id": "zookeeper", "name": "Zookeeper",
             "task_type": CollectPluginTypes.MIDDLEWARE,
             "type": CollectDriverTypes.JOB},
            {"id": "kafka", "model_id": "kafka", "name": "Kafka", "task_type": CollectPluginTypes.MIDDLEWARE,
             "type": CollectDriverTypes.JOB},
            {"id": "etcd", "model_id": "etcd", "name": "Etcd", "task_type": CollectPluginTypes.MIDDLEWARE,
             "type": CollectDriverTypes.JOB},
            {"id": "rabbitmq", "model_id": "rabbitmq", "name": "RabbitMQ", "task_type": CollectPluginTypes.MIDDLEWARE,
             "type": CollectDriverTypes.JOB},
            {"id": "tomcat", "model_id": "tomcat", "name": "Tomcat", "task_type": CollectPluginTypes.MIDDLEWARE,
             "type": CollectDriverTypes.JOB},
        ],
    }

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