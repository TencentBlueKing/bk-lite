K8S_WORKLOAD_REPLICASET = "prometheus_remote_write_kube_replicaset_created"
K8S_WORKLOAD_REPLICASET_OWNER = "prometheus_remote_write_kube_replicaset_owner"
K8S_POD_INFO = "prometheus_remote_write_kube_pod_info"
K8S_POD_CONTAINER_RESOURCE_LIMITS = "prometheus_remote_write_kube_pod_container_resource_limits"
K8S_POD_CONTAINER_RESOURCE_REQUESTS = "prometheus_remote_write_kube_pod_container_resource_requests"
K8S_NODE_INFO = "prometheus_remote_write_kube_node_info"
K8S_NODE_ROLE = "prometheus_remote_write_kube_node_role"
K8S_NODE_STATUS_CAPACITY = "prometheus_remote_write_kube_node_status_capacity"

K8S_STATEFULSET_REPLICAS = "prometheus_remote_write_kube_statefulset_replicas"
K8S_REPLICASET_REPLICAS = "prometheus_remote_write_kube_replicaset_spec_replicas"
K8S_DEPLOYMENT_REPLICAS = "prometheus_remote_write_kube_deployment_spec_replicas"

K8S_DEPLOYMENT_ANNOTATIONS = "prometheus_remote_write_kube_deployment_annotations"
K8S_DAEMONSET_ANNOTATIONS = "prometheus_remote_write_kube_daemonset_annotations"
K8S_STATEFULSET_ANNOTATIONS = "prometheus_remote_write_kube_statefulset_annotations"
K8S_JOB_ANNOTATIONS = "prometheus_remote_write_kube_job_annotations"
K8S_CRONJOB_ANNOTATIONS = "prometheus_remote_write_kube_cronjob_annotations"
K8S_REPLICASET_ANNOTATIONS = "prometheus_remote_write_kube_replicaset_annotations"

REPLICAS_METRICS = {K8S_STATEFULSET_REPLICAS, K8S_REPLICASET_REPLICAS, K8S_DEPLOYMENT_REPLICAS}
# workload 注解
ANNOTATIONS_METRICS = [
    K8S_DEPLOYMENT_ANNOTATIONS,
    K8S_DAEMONSET_ANNOTATIONS,
    K8S_STATEFULSET_ANNOTATIONS,
    K8S_JOB_ANNOTATIONS,
    K8S_CRONJOB_ANNOTATIONS,
    K8S_REPLICASET_ANNOTATIONS
]

COLLECTION_METRICS = {
    "namespace": ["prometheus_remote_write_kube_namespace_labels"],
    "workload": [
        "prometheus_remote_write_kube_deployment_created",
        "prometheus_remote_write_kube_daemonset_created",
        "prometheus_remote_write_kube_statefulset_created",
        "prometheus_remote_write_kube_job_info",
        "prometheus_remote_write_kube_cronjob_info",  # 未获取cronjob信息的指标
        K8S_WORKLOAD_REPLICASET,
        K8S_WORKLOAD_REPLICASET_OWNER,
        # replicas 数量
        # K8S_DEPLOYMENT_REPLICAS,
        # K8S_REPLICASET_REPLICAS,
        # K8S_STATEFULSET_REPLICAS
    ],
    "node": [K8S_NODE_INFO, K8S_NODE_ROLE, K8S_NODE_STATUS_CAPACITY],
    "pod": [K8S_POD_INFO, K8S_POD_CONTAINER_RESOURCE_LIMITS, K8S_POD_CONTAINER_RESOURCE_REQUESTS],
}
COLLECTION_METRICS["workload"].extend(ANNOTATIONS_METRICS)

WORKLOAD_TYPE_DICT = {
    "prometheus_remote_write_kube_deployment_created": "deployment",
    "prometheus_remote_write_kube_daemonset_created": "daemonset",
    "prometheus_remote_write_kube_statefulset_created": "statefulset",
    "prometheus_remote_write_kube_job_info": "job",
    "prometheus_remote_write_kube_cronjob_info": "cronjob",
    "prometheus_remote_write_kube_replicaset_created": "replicaset",
}

# workload name dict
WORKLOAD_NAME_DICT = {
    "prometheus_remote_write_kube_deployment_created": "deployment",
    "prometheus_remote_write_kube_daemonset_created": "daemonset",
    "prometheus_remote_write_kube_statefulset_created": "statefulset",
    "prometheus_remote_write_kube_job_info": "job_name",
    "prometheus_remote_write_kube_cronjob_info": "cronjob",
    "prometheus_remote_write_kube_replicaset_created": "replicaset",
}
# 统计副本数量的对象
REPLICAS_KEY = {"deployment", "replicaset", "statefulset"}
# namespace与cluster的关联关系
NAMESPACE_CLUSTER_RELATION = "k8s_namespace_belong_k8s_cluster"
# NAMESPACE_CLUSTER_RELATION = "k8s_cluster_belong_k8s_namespace"

# host与cluster的关联关系
NODE_CLUSTER_RELATION = "k8s_node_group_k8s_cluster"
# NODE_CLUSTER_RELATION = "k8s_cluster_group_k8s_node"

# workload与namespace的关联关系
WORKLOAD_NAMESPACE_RELATION = "k8s_workload_belong_k8s_namespace"
# WORKLOAD_NAMESPACE_RELATION = "k8s_namespace_belong_k8s_workload"

# workload与workload的关联关系
# WORKLOAD_WORKLOAD_RELATION = "k8s_workload_group_k8s_workload"

# pod与node的关联关系
POD_NODE_RELATION = "k8s_pod_run_k8s_node"
# POD_NODE_RELATION = "k8s_node_run_k8s_pod"

# pod与workload的关联关系
POD_WORKLOAD_RELATION = "k8s_pod_group_k8s_workload"
# POD_WORKLOAD_RELATION = "k8s_workload_group_k8s_pod"

# pod与namespace的关联关系
POD_NAMESPACE_RELATION = "k8s_pod_group_k8s_namespace"
# POD_NAMESPACE_RELATION = "k8s_namespace_group_k8s_pod"


VMWARE_CLUSTER = ["vmware_vc_info_gauge", "vmware_ds_info_gauge", "vmware_esxi_info_gauge", "vmware_vm_info_gauge"]

VMWARE_COLLECT_MAP = {
    "vmware_vc_info_gauge": "vmware_vc",
    "vmware_ds_info_gauge": "vmware_ds",
    "vmware_vm_info_gauge": "vmware_vm",
    "vmware_esxi_info_gauge": "vmware_esxi"
}

# "network_interfaces_info_gauge"
NETWORK_COLLECT = ["network_system_info_gauge", "network_interfaces_info_gauge"]
NETWORK_INTERFACES_RELATIONS = "network_topo_info_gauge"

PROTOCOL_METRIC_MAP = {
    "mysql": ["mysql_info_gauge"],
    "oracle": ["oracle_info_gauge"],
    "mssql": ["mssql_info_gauge"],
}

# aliyun
ALIYUN_COLLECT_CLUSTER = [
    "aliyun_ecs_info_gauge", "aliyun_bucket_info_gauge", "aliyun_mysql_info_gauge",
    "aliyun_pgsql_info_gauge", "aliyun_redis_info_gauge", "aliyun_mongodb_info_gauge",
    "aliyun_kafka_info_gauge", "aliyun_clb_info_gauge"
]

HOST_COLLECT_METRIC = ["host_info_gauge"]

DB_COLLECT_METRIC_MAP = {
    "es": ["es_info_gauge"],
    "redis": ["redis_info_gauge"],
    "mongodb": ["mongodb_info_gauge"],
    "postgresql": ["postgresql_info_gauge"],
    "dameng": ["dameng_info_gauge"],
    "db2": ["db2_info_gauge"],
    "tidb": ["tidb_info_gauge"],
    "hbase": ["hbase_info_gauge"],
}

MIDDLEWARE_METRIC_MAP = {
    "nginx" : ["nginx_info_gauge"],
    "zookeeper": ["zookeeper_info_gauge"],
    "kafka": ["kafka_info_gauge"],
    "etcd": ["etcd_info_gauge"],
    "rabbitmq": ["rabbitmq_info_gauge"],
    "tomcat": ["tomcat_info_gauge"],
    "apache": ["apache_info_gauge"],
    "activemq": ["activemq_info_gauge"],
    "weblogic": ["weblogic_info_gauge"],
    "keepalived": ["keepalived_info_gauge"],
    "tongweb": ["tongweb_info_gauge"],
    "jetty": ["jetty_info_gauge"],
}

# Tencent cloud
QCLOUD_COLLECT_CLUSTER = [
    "qcloud_cvm_info_gauge","qcloud_rocketmq_info_gauge","qcloud_mysql_info_gauge",
    "qcloud_redis_info_gauge","qcloud_mongodb_info_gauge","qcloud_pgsql_info_gauge",
    "qcloud_pulsar_cluster_info_gauge","qcloud_cmq_info_gauge","qcloud_cmq_topic_info_gauge",
    "qcloud_clb_info_gauge","qcloud_eip_info_gauge","qcloud_bucket_info_gauge","qcloud_filesystem_info_gauge",
    "qcloud_domain_info_gauge"
]

# AWS cloud
AWS_CLOUD_COLLECT_CLUSTER = [
    "aws_ec2_info_gauge",
    "aws_rds_info_gauge",
    "aws_msk_info_gauge",
    "aws_elasticache_info_gauge",
    "aws_eks_info_gauge",
    "aws_cloudfront_info_gauge",
    "aws_elb_info_gauge",
    "aws_s3_bucket_info_gauge",
    "aws_docdb_info_gauge",
    "aws_memdb_info_gauge",
]