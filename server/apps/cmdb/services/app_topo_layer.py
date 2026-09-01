from apps.core.exceptions.base_app_exception import BaseAppException

APP_TOPO_LAYER_SYSTEM = "system"
APP_TOPO_LAYER_SERVICE = "service"
APP_TOPO_LAYER_HOST = "host"
APP_TOPO_LAYER_APP_SERVICE = "appService"
APP_TOPO_LAYER_INFRASTRUCTURE = "infrastructure"
APP_TOPO_LAYER_NONE = "none"

APP_TOPO_LAYERS = (
    APP_TOPO_LAYER_SYSTEM,
    APP_TOPO_LAYER_SERVICE,
    APP_TOPO_LAYER_HOST,
    APP_TOPO_LAYER_APP_SERVICE,
    APP_TOPO_LAYER_INFRASTRUCTURE,
    APP_TOPO_LAYER_NONE,
)

APP_TOPO_LAYER_ALIASES = {
    APP_TOPO_LAYER_SYSTEM: APP_TOPO_LAYER_SYSTEM,
    APP_TOPO_LAYER_SERVICE: APP_TOPO_LAYER_SERVICE,
    APP_TOPO_LAYER_HOST: APP_TOPO_LAYER_HOST,
    APP_TOPO_LAYER_APP_SERVICE: APP_TOPO_LAYER_APP_SERVICE,
    APP_TOPO_LAYER_INFRASTRUCTURE: APP_TOPO_LAYER_INFRASTRUCTURE,
    APP_TOPO_LAYER_NONE: APP_TOPO_LAYER_NONE,
    "系统": APP_TOPO_LAYER_SYSTEM,
    "系统层": APP_TOPO_LAYER_SYSTEM,
    "服务": APP_TOPO_LAYER_SERVICE,
    "服务层": APP_TOPO_LAYER_SERVICE,
    "应用": APP_TOPO_LAYER_SERVICE,
    "主机": APP_TOPO_LAYER_HOST,
    "主机层": APP_TOPO_LAYER_HOST,
    "应用服务": APP_TOPO_LAYER_APP_SERVICE,
    "应用服务层": APP_TOPO_LAYER_APP_SERVICE,
    "基础设施": APP_TOPO_LAYER_INFRASTRUCTURE,
    "基础设施层": APP_TOPO_LAYER_INFRASTRUCTURE,
    "不分类": APP_TOPO_LAYER_NONE,
    "无": APP_TOPO_LAYER_NONE,
}

_APP_SERVICE_CLASSIFICATIONS = frozenset({"database", "middleware"})
_INFRA_CLASSIFICATIONS = frozenset({"harware", "hardware_components", "network_device", "idc"})
_HOST_LAYER_EXPLICIT = frozenset({"host", "manageone_server"})
_HOST_LAYER_SUFFIXES = ("_vm", "_ecs", "_cvm", "_ec2")

_CLOUD_APP_SERVICE_MODELS = frozenset(
    {
        "aliyun_mysql",
        "aliyun_pgsql",
        "aliyun_redis",
        "aliyun_mongodb",
        "aliyun_kafka_inst",
        "aws_rds",
        "aws_msk",
        "aws_elasticache",
        "aws_docdb",
        "aws_memdb",
        "azure_redis",
        "azure_mysql",
        "qcloud_mysql",
        "qcloud_rocketmq",
        "qcloud_redis",
        "qcloud_mongodb",
        "qcloud_pgsql",
        "qcloud_plusar_cluster",
        "qcloud_cmq",
        "qcloud_cmq_topic",
        "hwcloud_rds",
        "hwcloud_dcs",
    }
)

_APP_SERVICE_MODEL_IDS = (
    frozenset(
        {
            "mysql",
            "oracle",
            "mssql",
            "redis",
            "mongodb",
            "es",
            "postgresql",
            "db2",
            "tidb",
            "dameng",
            "hbase",
            "influxdb",
            "opengauss",
            "kingbase",
            "vastbase",
            "greenplum",
            "gbase8a",
            "oceanbase",
            "oceanbase_zone",
            "oceanbase_server",
            "oceanbase_tenant",
            "highgo",
            "informix",
            "sybase",
            "couchbase",
            "mycat",
            "sap_hana",
            "iris",
            "redis_sentinel",
            "gbase8s",
            "oscar",
            "tongrds",
            "tdsql",
            "apache",
            "tomcat",
            "nginx",
            "iis",
            "weblogic",
            "websphere",
            "tongweb",
            "kafka",
            "zookeeper",
            "rabbitmq",
            "activemq",
            "etcd",
            "keepalive",
            "tuxedo",
            "jetty",
            "memcached",
            "rocketmq",
            "openresty",
            "ceph",
            "jboss",
            "squid",
            "haproxy",
            "spark",
            "minio",
            "nacos",
            "nacos_node",
            "nacos_namespace",
            "nacos_service",
            "ibmmq",
            "ibmmq_channel",
            "ibmmq_listener",
            "ibmmq_localqueue",
            "ibmmq_remotequeue",
            "tonglinkq",
            "tonggtp",
            "ihs",
            "cics",
            "hdfs",
            "yarn",
            "storm",
            "ambari",
            "bes",
            "apusic",
            "inforsuite_as",
        }
    )
    | _CLOUD_APP_SERVICE_MODELS
)

_INFRA_MODEL_IDS = frozenset(
    {
        "physcial_server",
        "storage",
        "server_bmc",
        "tape_library",
        "disk",
        "memory",
        "nic",
        "gpu",
        "storage_pool",
        "storage_disk",
        "storage_volume",
        "server_bmc_cpu",
        "server_bmc_memory",
        "server_bmc_disk",
        "server_bmc_vdisk",
        "server_bmc_nic",
        "switch",
        "router",
        "firewall",
        "loadbalance",
        "interface",
        "security_device",
        "datacenter",
        "server_room",
        "rack",
    }
)


def _is_host_layer_model(model_id: str) -> bool:
    if model_id in _HOST_LAYER_EXPLICIT:
        return True
    return model_id.endswith(_HOST_LAYER_SUFFIXES)


def default_app_topo_layer(model_id: str, classification_id: str = "") -> str:
    model_id = model_id or ""
    classification_id = classification_id or ""
    if model_id == "system":
        return APP_TOPO_LAYER_SYSTEM
    if model_id == "application":
        return APP_TOPO_LAYER_SERVICE
    if _is_host_layer_model(model_id):
        return APP_TOPO_LAYER_HOST
    if classification_id in _APP_SERVICE_CLASSIFICATIONS or model_id in _APP_SERVICE_MODEL_IDS:
        return APP_TOPO_LAYER_APP_SERVICE
    if classification_id in _INFRA_CLASSIFICATIONS or model_id in _INFRA_MODEL_IDS:
        return APP_TOPO_LAYER_INFRASTRUCTURE
    return APP_TOPO_LAYER_NONE


def normalize_app_topo_layer(value) -> str:
    if value in (None, ""):
        return APP_TOPO_LAYER_NONE
    key = str(value).strip()
    layer = APP_TOPO_LAYER_ALIASES.get(key)
    if layer is None:
        raise BaseAppException("应用拓扑层级不合法")
    return layer


def resolve_app_topo_layer(model_id: str, stored_value=None, classification_id: str = "") -> str:
    if stored_value in (None, ""):
        return default_app_topo_layer(model_id, classification_id)
    return normalize_app_topo_layer(stored_value)
