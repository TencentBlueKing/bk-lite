# -- coding: utf-8 --
# @File: k8s.py
# @Time: 2025/11/12 13:49
# @Author: windyzhao

# -- coding: utf-8 --
# @File: k8s.py
# @Time: 2025/11/12 11:39
# @Author: windyzhao
import json

from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.query_vm import Collection

from apps.cmdb.collection.constants import (
    COLLECTION_METRICS,
    NAMESPACE_CLUSTER_RELATION,
    NODE_CLUSTER_RELATION,
    POD_NAMESPACE_RELATION,
    POD_WORKLOAD_RELATION,
    WORKLOAD_NAME_DICT,
    WORKLOAD_NAMESPACE_RELATION,
    WORKLOAD_TYPE_DICT, K8S_WORKLOAD_REPLICASET, K8S_WORKLOAD_REPLICASET_OWNER, K8S_POD_INFO,
    K8S_POD_CONTAINER_RESOURCE_LIMITS,
    K8S_POD_CONTAINER_RESOURCE_REQUESTS, K8S_NODE_ROLE, K8S_NODE_INFO, K8S_NODE_STATUS_CAPACITY, REPLICAS_KEY,
    REPLICAS_METRICS, K8S_STATEFULSET_REPLICAS, K8S_REPLICASET_REPLICAS, K8S_DEPLOYMENT_REPLICAS, ANNOTATIONS_METRICS,
    K8S_DEPLOYMENT_ANNOTATIONS, K8S_REPLICASET_ANNOTATIONS, K8S_STATEFULSET_ANNOTATIONS, K8S_DAEMONSET_ANNOTATIONS,
    K8S_JOB_ANNOTATIONS, K8S_CRONJOB_ANNOTATIONS, POD_NODE_RELATION
)
from apps.core.logger import cmdb_logger as logger


class CollectK8sMetrics:
    _MODEL_ID = "k8s_cluster"

    def __init__(self, cluster_name, *args, **kwargs):
        self.cluster_name = cluster_name
        self.metrics = self.get_metrics()
        self.collection_metrics_dict = {i: [] for i in COLLECTION_METRICS.keys()}
        self.timestamp_gt = False
        self.result = {}

    @property
    def collect_data(self):
        """采集数据"""
        data = {
            "k8s_node": self.collection_metrics_dict["node"],
            "k8s_pod": self.collection_metrics_dict["pod"],
            "k8s_workload": self.collection_metrics_dict["workload"],
            "k8s_namespace": self.collection_metrics_dict["namespace"]
        }
        return data

    @property
    def collect_params(self):
        params = {
            "node": "k8s_node",
            "pod": "k8s_pod",
            "namespace": "k8s_namespace",
            "workload": "k8s_workload",
        }
        return params

    @staticmethod
    def get_metrics():
        metrics = []
        metrics.extend(COLLECTION_METRICS["namespace"])
        metrics.extend(COLLECTION_METRICS["workload"])
        metrics.extend(COLLECTION_METRICS["node"])
        metrics.extend(COLLECTION_METRICS["pod"])
        return metrics

    def query_data(self):
        """查询数据"""
        sql = " or ".join(
            "{}{{instance_id=\"{}\"}}".format(j, self.cluster_name) for m in COLLECTION_METRICS.values() for j in m)
        data = Collection().query(sql)
        return data.get("data", [])

    def format_data(self, data):
        """格式化数据"""

        for index_data in data["result"]:
            metric_name = index_data["metric"]["__name__"]
            value = index_data["value"]
            _time, value = value[0], value[1]
            if not self.timestamp_gt:
                if timestamp_gt_one_day_ago(_time):
                    break
                else:
                    self.timestamp_gt = True

            index_dict = dict(
                index_key=metric_name,
                index_value=value,
                # index_time=index_data["TimeUnix"],
                **index_data["metric"],
            )
            if metric_name in COLLECTION_METRICS["namespace"]:
                self.collection_metrics_dict["namespace"].append(index_dict)
            elif metric_name in COLLECTION_METRICS["workload"]:
                self.collection_metrics_dict["workload"].append(index_dict)
            elif metric_name in COLLECTION_METRICS["node"]:
                self.collection_metrics_dict["node"].append(index_dict)
            elif metric_name in COLLECTION_METRICS["pod"]:
                self.collection_metrics_dict["pod"].append(index_dict)

        self.format_namespace_metrics()
        self.format_pod_metrics()
        self.format_node_metrics()
        self.format_workload_metrics()

    def format_namespace_metrics(self):
        """格式化namespace namespace.inst_name={namespace.name}（{cluster.inst_name}）"""
        result = []
        for index_data in self.collection_metrics_dict["namespace"]:
            result.append(
                dict(
                    inst_name=f"{index_data['namespace']}({self.cluster_name})",
                    self_cluster=self.cluster_name,
                    name=index_data["namespace"],
                    assos=[
                        {

                            "self_cluster": self.cluster_name,
                            "model_id": "k8s_cluster",
                            "inst_name": self.cluster_name,
                            "asst_id": "belong",
                            "model_asst_id": NAMESPACE_CLUSTER_RELATION,
                        }
                    ],
                )
            )
        self.collection_metrics_dict["namespace"] = result
        self.result["k8s_namespace"] = result

    def search_replicas(self):
        """查询副本数量"""
        replicas_metrics = []
        sql = " or ".join(
            "{}{{instance_id=\"{}\"}}".format(m, self.cluster_name) for m in REPLICAS_METRICS)
        data = Collection().query(sql)
        replicas_data = data.get("data", [])
        for index_data in replicas_data["result"]:
            metric_name = index_data["metric"]["__name__"]
            value = index_data["value"]
            _time, value = value[0], value[1]
            if timestamp_gt_one_day_ago(_time):
                break
            index_dict = dict(
                index_key=metric_name,
                index_value=value,
                **index_data["metric"],
            )
            replicas_metrics.append(index_dict)

        # 构建副本数量映射关系
        replicas_map = {}
        for replicas_info in replicas_metrics:
            if replicas_info["index_key"] == K8S_STATEFULSET_REPLICAS:
                replicas_key = "statefulset"
            elif replicas_info["index_key"] == K8S_REPLICASET_REPLICAS:
                replicas_key = "replicaset"
            elif replicas_info["index_key"] == K8S_DEPLOYMENT_REPLICAS:
                replicas_key = "deployment"
            else:
                continue

            replicas_key_name = replicas_info[replicas_key]
            replicas_map.setdefault(replicas_key, {}).update({replicas_key_name: replicas_info["index_value"]})

        return replicas_map

    @staticmethod
    def format_annotation_metrics(metrics):
        """格式化注解指标"""
        labels = ""
        metric_key = "annotation_kubectl_kubernetes_io_last_applied_configuration"
        if metric_key not in metrics:
            return labels

        annotation = metrics[metric_key]
        try:
            annotation = json.loads(annotation.replace(r"\n", ""))
        except:  # noqa
            return labels

        try:
            if annotation['spec']['template']['metadata'].get('labels', False):
                labels_list = []
                for k, v in annotation['spec']['template']['metadata']['labels'].items():
                    labels_list.append(f"{k}={v}")

                labels = ','.join(labels_list)
        except:  # noqa
            pass
        return labels

    def format_workload_metrics(self):
        """格式化workload，优化关联关系处理和数据完整性"""
        # 用于存储ReplicaSet的所有者信息
        replicaset_owner_dict = {}
        # 分别存储ReplicaSet和其他workload的指标
        replicaset_metrics = []
        workload_metrics = []
        annotations_metrics = []

        # 首先对指标进行分类
        for index_data in self.collection_metrics_dict["workload"]:
            if index_data["index_key"] == K8S_WORKLOAD_REPLICASET:
                replicaset_metrics.append(index_data)
            elif index_data["index_key"] == K8S_WORKLOAD_REPLICASET_OWNER:
                # 使用(namespace, replicaset)作为键存储所有者信息
                key = (index_data["namespace"], index_data["replicaset"])
                replicaset_owner_dict[key] = {
                    "owner_kind": index_data["owner_kind"].lower(),
                    "owner_name": index_data["owner_name"]
                }
            elif index_data["index_key"] in ANNOTATIONS_METRICS:
                # 单独存储注解指标
                index_data.update(_annotation=self.format_annotation_metrics(index_data))
                annotations_metrics.append(index_data)
            else:
                workload_metrics.append(index_data)

        # 构建注解映射关系
        annotations_map = {}
        for annotations_info in annotations_metrics:
            if annotations_info["index_key"] == K8S_STATEFULSET_ANNOTATIONS:
                replicas_key = "statefulset"
            elif annotations_info["index_key"] == K8S_REPLICASET_ANNOTATIONS:
                replicas_key = "replicaset"
            elif annotations_info["index_key"] == K8S_DEPLOYMENT_ANNOTATIONS:
                replicas_key = "deployment"
            elif annotations_info["index_key"] == K8S_DAEMONSET_ANNOTATIONS:
                replicas_key = "daemonset"
            elif annotations_info["index_key"] == K8S_JOB_ANNOTATIONS:
                replicas_key = "job"
            elif annotations_info["index_key"] == K8S_CRONJOB_ANNOTATIONS:
                replicas_key = "cronjob"
            else:
                continue

            annotations_key_name = annotations_info[replicas_key]
            annotations_map.setdefault(replicas_key, {}).update({annotations_key_name: annotations_info["_annotation"]})

        replicas_map = self.search_replicas()
        result = []
        # 处理非ReplicaSet的workload
        for workload_info in workload_metrics:
            inst_name_key = WORKLOAD_NAME_DICT[workload_info["index_key"]]
            namespace = f"{workload_info['instance_id']}/{workload_info['namespace']}"

            replicas = 0
            if inst_name_key in REPLICAS_KEY:
                replicas = replicas_map.get(inst_name_key, {}).get(workload_info[inst_name_key], 0)

            inst_name = f"{workload_info[inst_name_key]}({self.cluster_name}/{workload_info['namespace']})"
            workload_type = WORKLOAD_TYPE_DICT[workload_info["index_key"]]
            name = workload_info[inst_name_key]
            result.append({
                "inst_name": inst_name,
                "name": name,
                "workload_type": workload_type,
                "self_ns": namespace,
                "labels": annotations_map.get(inst_name_key, {}).get(workload_info[inst_name_key], ""),
                "self_cluster": self.cluster_name,
                "replicas": int(replicas),
                "assos": [{
                    "model_id": "k8s_namespace",
                    "inst_name": f"{workload_info['namespace']}({self.cluster_name})",
                    "asst_id": "belong",
                    "model_asst_id": WORKLOAD_NAMESPACE_RELATION
                }]
            })

        # 处理ReplicaSet
        for rs_info in replicaset_metrics:
            inst_name_key = WORKLOAD_NAME_DICT[rs_info["index_key"]]
            namespace = f"{rs_info['instance_id']}/{rs_info['namespace']}"
            key = (rs_info["namespace"], rs_info["replicaset"])
            owner = replicaset_owner_dict.get(key)

            replicas = replicas_map.get(inst_name_key, {}).get(rs_info[inst_name_key], 0)

            if owner and owner["owner_kind"] in WORKLOAD_TYPE_DICT.values():
                # 有有效所有者的ReplicaSet
                inst_name = f"{rs_info[inst_name_key]}({self.cluster_name}/{owner['owner_name']})"
                workload_type = owner["owner_kind"]
                name = owner["owner_name"]

                result.append({
                    "inst_name": inst_name,
                    "name": name,
                    "labels": annotations_map.get(inst_name_key, {}).get(rs_info[inst_name_key], ""),
                    "workload_type": workload_type,
                    "k8s_namespace": namespace,
                    "replicaset_name": rs_info["replicaset"],
                    "self_ns": namespace,
                    "self_cluster": self.cluster_name,
                    "replicas": int(replicas),
                    "assos": [{
                        "model_id": "k8s_namespace",
                        "inst_name": f"{rs_info['namespace']}({self.cluster_name})",
                        "asst_id": "belong",
                        "model_asst_id": WORKLOAD_NAMESPACE_RELATION
                    }]
                })
            else:
                # 没有有效所有者的ReplicaSet，作为独立workload处理
                logger.warning(
                    f"ReplicaSet {rs_info['replicaset']} 在命名空间 {rs_info['namespace']} 中没有有效的所有者信息，将作为独立workload处理")

                inst_name = f"{rs_info[inst_name_key]}({self.cluster_name}/{rs_info['namespace']})"
                workload_type = "replicaset"  # 明确标记为replicaset类型
                name = rs_info["replicaset"]

                result.append({
                    "inst_name": inst_name,
                    "name": name,
                    "labels": annotations_map.get(inst_name_key, {}).get(rs_info[inst_name_key], ""),
                    "workload_type": workload_type,
                    "k8s_namespace": namespace,
                    "replicaset_name": rs_info["replicaset"],
                    "self_ns": namespace,
                    "self_cluster": self.cluster_name,
                    "replicas": int(replicas),
                    "assos": [{
                        "model_id": "k8s_namespace",
                        "inst_name": f"{rs_info['namespace']}({self.cluster_name})",
                        "asst_id": "belong",
                        "model_asst_id": WORKLOAD_NAMESPACE_RELATION
                    }]
                })

        self.collection_metrics_dict["workload"] = result
        self.result["k8s_workload"] = result

    def format_pod_metrics(self):
        """
        格式化pod信息，优化关联关系处理
        主要改进：
        1. 简化资源信息处理逻辑
        2. 优化关联关系的建立
        3. 增加通过ReplicaSet关联Deployment的逻辑
        """
        # 用于存储不同类型的Pod信息
        pod_info = []
        resource_limits = {}
        resource_requests = {}

        # 1. 分类处理Pod相关指标
        for index_data in self.collection_metrics_dict["pod"]:
            if index_data["index_key"] == K8S_POD_INFO:
                pod_info.append(index_data)
            elif index_data["index_key"] == K8S_POD_CONTAINER_RESOURCE_LIMITS:
                resource_limits[(index_data["pod"], index_data["resource"])] = index_data["index_value"]
            elif index_data["index_key"] == K8S_POD_CONTAINER_RESOURCE_REQUESTS:
                resource_requests[(index_data["pod"], index_data["resource"])] = index_data["index_value"]

        # 2. 构建workload查找索引（通过workload结果中的replicaset_name）
        workload_index = {}
        for workload in self.collection_metrics_dict["workload"]:
            if "replicaset" in workload:
                workload_index[workload["replicaset"]] = workload

        result = []
        for pod in pod_info:
            namespace = f"{pod['namespace']}/({self.cluster_name})"

            # 3. 构建基础Pod信息
            # pod.inst_name={pod.name}({cluster.inst_name or namespace.self_cluster}/{namespace.name})
            pod_data = {
                "inst_name": f"{pod['pod']}({self.cluster_name}/{pod['namespace']})",
                "name": pod["pod"],
                "ip_addr": pod.get("pod_ip", ""),
                "namespace": pod["namespace"],
                "node": pod.get("node"),
                "created_by_kind": pod.get("created_by_kind", "").lower(),
                "created_by_name": pod.get("created_by_name"),
                "self_ns": namespace,
                "self_cluster": self.cluster_name,
            }

            # 4. 处理资源配额信息
            for resource_type in ["cpu", "memory"]:
                # 处理限制资源
                limit_value = resource_limits.get((pod["pod"], resource_type))
                if limit_value:
                    if resource_type == "memory":
                        limit_value = int(float(limit_value) / 1024 ** 3)
                    else:
                        limit_value = float(limit_value)
                    pod_data[f"limit_{resource_type}"] = limit_value

                # 处理请求资源
                request_value = resource_requests.get((pod["pod"], resource_type))
                if request_value:
                    if resource_type == "memory":
                        request_value = int(float(request_value) / 1024 ** 3)
                    else:
                        request_value = float(request_value)
                    pod_data[f"request_{resource_type}"] = request_value

            # 5. 建立关联关系
            associations = []

            # 添加Node关联
            if pod_data["node"]:
                associations.append({
                    "model_id": "k8s_node",
                    "inst_name": f"{pod_data['node']}({self.cluster_name})",
                    "asst_id": "run",
                    "model_asst_id": POD_NODE_RELATION
                })

            # 处理工作负载关联
            if pod_data["created_by_kind"] == "replicaset":
                # 通过ReplicaSet找到对应的Deployment
                workload = workload_index.get(pod_data["created_by_name"])
                if workload:
                    pod_data["k8s_workload"] = workload["owner_name"]
                    associations.append({
                        "model_id": "k8s_workload",
                        "inst_name": f"{workload['owner_name']}({self.cluster_name}/{pod_data['namespace']})",
                        "asst_id": "group",
                        "model_asst_id": POD_WORKLOAD_RELATION
                    })
                else:
                    # 如果找不到对应的Deployment，关联到命名空间
                    pod_data["k8s_namespace"] = namespace
                    associations.append({
                        "model_id": "k8s_namespace",
                        "inst_name": f"{pod_data['namespace']}({self.cluster_name})",
                        "asst_id": "group",
                        "model_asst_id": POD_NAMESPACE_RELATION
                    })
            elif pod_data["created_by_kind"] in WORKLOAD_TYPE_DICT.values():
                # 直接关联到其他类型的工作负载
                pod_data["k8s_workload"] = pod_data["created_by_name"]
                associations.append({
                    "model_id": "k8s_workload",
                    "inst_name": f"{pod_data['created_by_name']}({self.cluster_name}/{pod_data['namespace']})",
                    "asst_id": "group",
                    "model_asst_id": POD_WORKLOAD_RELATION
                })
            else:
                # 其他情况关联到命名空间
                pod_data["k8s_namespace"] = namespace
                associations.append({
                    "model_id": "k8s_namespace",
                    "inst_name": namespace,
                    "asst_id": "group",
                    "model_asst_id": POD_NAMESPACE_RELATION
                })

            pod_data["assos"] = associations
            result.append(pod_data)

        self.collection_metrics_dict["pod"] = result
        self.result["k8s_pod"] = result

    def format_node_metrics(self):
        """格式化node"""
        inst_index_info_list, inst_resource_dict, inst_role_dict = [], {}, {}
        for index_data in self.collection_metrics_dict["node"]:
            if index_data["index_key"] == K8S_NODE_INFO:
                inst_index_info_list.append(index_data)
            elif index_data["index_key"] == K8S_NODE_ROLE:
                if index_data["node"] not in inst_role_dict:
                    inst_role_dict[index_data["node"]] = []
                inst_role_dict[index_data["node"]].append(index_data["role"])
            elif index_data["index_key"] == K8S_NODE_STATUS_CAPACITY:
                inst_resource_dict[(index_data["node"], index_data["resource"])] = index_data["index_value"]
        result = []
        for inst_index_info in inst_index_info_list:
            # node.inst_name={node.name}({cluster.inst_name})
            info = dict(
                inst_name=f"{inst_index_info['node']}({self.cluster_name})",
                name=inst_index_info["node"],
                ip_addr=inst_index_info.get("internal_ip"),
                os_version=inst_index_info.get("os_image"),
                kernel_version=inst_index_info.get("kernel_version"),
                kubelet_version=inst_index_info.get("kubelet_version"),
                container_runtime_version=inst_index_info.get("container_runtime_version"),
                pod_cidr=inst_index_info.get("pod_cidr"),
                self_cluster=self.cluster_name,
                assos=[
                    {
                        "model_id": "k8s_cluster",
                        "inst_name": self.cluster_name,
                        "asst_id": "group",
                        "model_asst_id": NODE_CLUSTER_RELATION,
                    }
                ],
            )
            info = {k: v for k, v in info.items() if v}
            cpu = inst_resource_dict.get((inst_index_info["node"], "cpu"))
            if cpu:
                info.update(cpu=int(cpu))
            memory = inst_resource_dict.get((inst_index_info["node"], "memory"))
            if memory:
                info.update(memory=int(float(memory) / 1024 ** 3))
            disk = inst_resource_dict.get((inst_index_info["node"], "ephemeral_storage"))
            if disk:
                info.update(storage=int(float(disk) / 1024 ** 3))
            role = ",".join(inst_role_dict.get(inst_index_info["node"], []))
            if role:
                info.update(role=role)
            result.append(info)
        self.collection_metrics_dict["node"] = result
        self.result["k8s_node"] = result

    def run(self):
        """执行"""
        data = self.query_data()
        self.format_data(data)
        return self.result
