import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Type

from apps.cmdb.collection.base import timestamp_gt_one_day_ago, CollectBase, Collection
from apps.cmdb.collection.common import Management
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
    K8S_JOB_ANNOTATIONS, K8S_CRONJOB_ANNOTATIONS, POD_NODE_RELATION, VMWARE_CLUSTER, VMWARE_COLLECT_MAP,
    NETWORK_COLLECT, NETWORK_INTERFACES_RELATIONS, PROTOCOL_METRIC_MAP, ALIYUN_COLLECT_CLUSTER, HOST_COLLECT_METRIC,
    MIDDLEWARE_METRIC_MAP, QCLOUD_COLLECT_CLUSTER, DB_COLLECT_METRIC_MAP,
)
from apps.cmdb.constants import INSTANCE
from apps.cmdb.graph.neo4j import Neo4jClient
from apps.cmdb.models import OidMapping
from apps.core.logger import cmdb_logger as logger


# 指标纳管（纳管控制器）
class MetricsCannula:
    def __init__(self, inst_id, organization: list, inst_name: str, task_id: int, collect_plugin: Type,
                 manual: bool = False, default_metrics: dict = None, filter_collect_task=True):
        self.inst_id = inst_id
        self.organization = organization
        self.task_id = str(task_id)
        self.manual = False if default_metrics else manual  # 是否手动
        self.inst_name = inst_name
        self.collect_plugin = collect_plugin
        self.filter_collect_task = filter_collect_task
        self.collect_data = {}  # 采集后的原始数据
        self.collect_params = {}
        self.collection_metrics = default_metrics or self.get_collection_metrics()
        self.now_time = datetime.now(timezone.utc).isoformat()
        self.add_list = []
        self.update_list = []
        self.delete_list = []
        self.assos_list = []

    def get_collection_metrics(self):
        """获取采集指标"""
        new_metrics = self.collect_plugin(self.inst_name, self.inst_id, self.task_id)
        result = new_metrics.run()
        self.collect_data = new_metrics.result
        return result

    @staticmethod
    def contrast(old_map, new_map):
        """数据对比"""
        add_list, update_list, delete_list = [], [], []
        for key, info in new_map.items():
            if key not in old_map:
                add_list.append(info)
            else:
                info.update(_id=old_map[key]["_id"])
                update_list.append(info)
        for key, info in old_map.items():
            if key not in new_map:
                delete_list.append(info)
        return add_list, update_list, delete_list

    def collect_controller(self) -> dict:
        result = {}
        for model_id, metrics in self.collection_metrics.items():
            params = [
                {"field": "model_id", "type": "str=", "value": model_id},
            ]
            if self.filter_collect_task:
                params.append({"field": "collect_task", "type": "str=", "value": self.task_id})

            with Neo4jClient() as ag:
                already_data, _ = ag.query_entity(INSTANCE, params)
                management = Management(
                    self.organization,
                    self.inst_name,
                    model_id,
                    already_data,
                    metrics,
                    ["inst_name"],
                    self.now_time,
                    self.task_id,
                    collect_plugin=self.collect_plugin
                )
                if self.manual:
                    self.add_list.extend(management.add_list)
                    self.delete_list.extend(management.delete_list)
                    # 只更新数据 对于删除创建的数据不做处理
                    collect_result = management.update()
                else:
                    collect_result = management.controller()

                result[model_id] = collect_result

        return result


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
        """格式化workload，简化关联关系处理"""
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

            if owner and owner["owner_kind"] in WORKLOAD_TYPE_DICT.values():
                replicas = replicas_map.get(inst_name_key, {}).get(rs_info[inst_name_key], 0)

                inst_name = f"{rs_info[inst_name_key]}({self.cluster_name}/{owner['owner_name']})"
                workload_type = owner["owner_kind"]
                name = owner["owner_name"]

                # 只添加有效的所有者关联
                result.append({
                    "inst_name": inst_name,
                    "name": name,
                    "labels": annotations_map.get(inst_name_key, {}).get(rs_info[inst_name_key], ""),
                    "workload_type": workload_type,
                    "k8s_namespace": namespace,
                    "replicaset_name": rs_info["replicaset"],  # 保存ReplicaSet名称用于Pod关联
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


class CollectVmwareMetrics(CollectBase):
    _MODEL_ID = "vmware_vc"

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.model_resource_id_mapping = {}

    @property
    def _metrics(self):
        return VMWARE_CLUSTER

    def get_esxi_asso(self, data, *args, **kwargs):
        vmware_ds = data.get("vmware_ds", "")
        vmware_ds_list = vmware_ds.split(",")
        result = [
            {
                "model_id": "vmware_vc",
                "inst_name": self.inst_name,
                "asst_id": "group",
                "model_asst_id": "vmware_esxi_group_vmware_vc",
            }
        ]
        for ds in vmware_ds_list:
            inst_name = self.model_resource_id_mapping["vmware_ds"].get(ds, "")
            result.append({
                "model_id": "vmware_ds",
                "inst_name": inst_name,
                "asst_id": "connect",
                "model_asst_id": "vmware_esxi_connect_vmware_ds"
            })
        return result

    def get_vm_asso(self, data, *args, **kwargs):
        result = []
        esxi_inst_name = self.model_resource_id_mapping["vmware_esxi"].get(data["vmware_esxi"], "")
        if esxi_inst_name:
            result.append({
                "model_id": "vmware_esxi",
                "inst_name": esxi_inst_name,
                "asst_id": "run",
                "model_asst_id": "vmware_vm_run_vmware_esxi"
            })

        vmware_esxi_list = data["vmware_ds"].split(",")
        for ds in vmware_esxi_list:
            inst_name = self.model_resource_id_mapping["vmware_ds"].get(ds, "")
            if not inst_name:
                continue
            result.append({
                "model_id": "vmware_ds",
                "inst_name": inst_name,
                "asst_id": "connect",
                "model_asst_id": "vmware_vm_connect_vmware_ds"
            })
        return result

    @staticmethod
    def set_inst_name(*args, **kwargs):
        """
        {vm的名称}[{moid}]
        """
        data = args[0]
        inst_name = f"{data['inst_name']}[{data['resource_id']}]"
        return inst_name

    @property
    def model_field_mapping(self):
        mapping = {
            "vmware_vc": {
                "vc_version": "vc_version",
                "inst_name": self.inst_name
            },
            "vmware_vm": {
                "inst_name": "inst_name",
                "ip_addr": "ip_addr",
                "resource_id": "resource_id",
                "os_name": "os_name",
                "vcpus": (int, "vcpus"),
                "memory": (int, "memory"),
                self.asso: self.get_vm_asso
            },
            "vmware_esxi": {
                "inst_name": "inst_name",
                "ip_addr": "ip_addr",
                "resource_id": "resource_id",
                "cpu_cores": (int, "cpu_cores"),
                "vcpus": (int, "vcpus"),
                "memory": (int, "memory"),
                "esxi_version": "esxi_version",
                self.asso: self.get_esxi_asso

            },
            "vmware_ds": {
                "inst_name": "inst_name",
                "system_type": "system_type",
                "resource_id": "resource_id",
                "storage": (int, "storage"),
                "url": "url",
                # self.asso: self.get_ds_asso
            }

        }

        return mapping

    def prom_sql(self):
        sql = " or ".join(
            "{}{{instance_id=\"{}\"}}".format(m, f"{self.task_id}_{self.inst_name}") for m in self._metrics)
        return sql

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
                **index_data["metric"],
            )

            self.collection_metrics_dict[metric_name].append(index_dict)

    def format_metrics(self):
        """格式化数据"""
        for metric_key, metrics in self.collection_metrics_dict.items():
            model_id = VMWARE_COLLECT_MAP[metric_key]
            result = []
            if model_id == "vmware_vc":
                self.model_resource_id_mapping.update({model_id: {}})
            else:
                self.model_resource_id_mapping.update({model_id: {i["resource_id"]: i["inst_name"] for i in metrics}})
            mapping = self.model_field_mapping.get(model_id, {})
            for index_data in metrics:
                data = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data[key_or_func[1]])
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data, index_data["inst_name"])
                    else:
                        data[field] = index_data.get(key_or_func, "")

                result.append(data)
            self.result[model_id] = result


class CollectNetworkMetrics(CollectBase):
    ROOT = "root"  # 根oid
    KEY = "key"  # oid
    TAG = "tag"  # 名称
    IF_INDEX = "ifindex"  # 索引
    IF_INDEX_TYPE = "ifindex_type"  # 索引类型 default为单索引,ipaddr为后4位为ip地址
    VAL = "val"  # oid对应值

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.oid_map = self.get_oid_map()
        # 4：other  （冗余用的）
        self.interface_status_map = {
            "1": "UP",
            "2": "Down",
            "3": "Testing"
        }
        self.instance_id_map = {}
        self.collect_inst = self.get_collect_inst()
        self.is_topo = self.collect_inst.is_network_topo
        self.set_metrics()
        self.interfaces_data = {}

    def set_metrics(self):
        if self.is_topo:
            self._metrics.append(NETWORK_INTERFACES_RELATIONS)
            self.collection_metrics_dict.update({NETWORK_INTERFACES_RELATIONS: []})

    @property
    def _metrics(self):
        return NETWORK_COLLECT

    def prom_sql(self):
        sql = " or ".join(m for m in self._metrics)
        return sql

    @staticmethod
    def get_oid_map():
        result = OidMapping.objects.all().values()
        return {i["oid"]: i for i in result}

    @staticmethod
    def set_inst_name(*args, **kwargs):
        # ip-switch
        data = args[0]
        inst_name = f"{data['ip_addr']}-{data['device_type']}"
        return inst_name

    def set_interface_status(self, data, *args, **kwargs):
        return self.interface_status_map.get(data, "other")

    def set_interface_inst_name(self, data, *args, **kwargs):
        inst_name = self.set_self_device(data)
        return f"{inst_name}-{data.get('alias', data['description'])}"

    def set_self_device(self, data, *args, **kwargs):
        instance_id = data["instance_id"]
        instance = self.instance_id_map[instance_id]
        return self.set_inst_name(instance)

    def get_interface_asso(self, data, *args, **kwargs):
        instance_id = data["instance_id"]
        instance = self.instance_id_map[instance_id]
        model_id = instance["device_type"]
        return [
            {
                "model_id": model_id,
                "inst_name": self.set_inst_name(instance),
                "asst_id": "belong",
                "model_asst_id": f"interface_belong_{model_id}"
            }
        ]

    @property
    def device_map(self):
        # 网络设备
        mapping = {
            "inst_name": self.set_inst_name,
            "ip_addr": "ip_addr",
            "soid": "sysobjectid",
            "port": "port",
            "model": "model",
            "brand": "brand",
            "model_id": "model_id"
        }
        return mapping

    @staticmethod
    def interface_name(data, *args, **kwargs):
        return data.get("alias", data['description'])

    @property
    def model_field_mapping(self):
        # 接口
        mapping = {
            "inst_name": self.set_interface_inst_name,
            "self_device": self.set_self_device,
            "mac": "mac_address",
            "name": self.interface_name,
            "status": (self.set_interface_status, "oper_status"),
            self.asso: self.get_interface_asso,
        }
        return mapping

    def check_task_id(self, instance_id):
        # TODO 后续补tag字段后 修改查询的promsql 语句
        task_id, _ = instance_id.split("_", 1)
        return task_id == self.task_id

    def format_data(self, data):
        """格式化数据"""
        for index_data in data["result"]:
            metric_name = index_data["metric"]["__name__"]
            instance_id = index_data["metric"]["instance_id"]
            if not self.check_task_id(instance_id):
                continue

            if "sysobjectid" in index_data["metric"]:
                oid = index_data["metric"]["sysobjectid"]
                oid_data = self.oid_map.get(oid, "")
                if not oid_data:
                    logger.info("==OID does not exist, this instance data is skipped OID={}==".format(oid))
                    continue
                else:
                    index_data["metric"].update(oid_data)

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
                **index_data["metric"],
            )

            if "sysobjectid" in index_dict:
                self.instance_id_map[index_dict["instance_id"]] = index_dict

            self.collection_metrics_dict[metric_name].append(index_dict)

    def format_metrics(self):
        """格式化数据"""
        topo_data = self.collection_metrics_dict.pop(NETWORK_INTERFACES_RELATIONS, [])
        for metric_key, metrics in self.collection_metrics_dict.items():
            for index_data in metrics:
                if index_data["instance_id"] not in self.instance_id_map:
                    logger.info(
                        "This data is discarded because no feature library can be found for the OID. instance_id={}".format(
                            index_data["instance_id"]))
                    continue
                if "sysobjectid" in index_data:
                    model_id = index_data["device_type"]
                    mapping = self.device_map
                else:
                    model_id = "interface"
                    mapping = self.model_field_mapping

                data = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data[key_or_func[1]])
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data)
                    else:
                        data[field] = index_data.get(key_or_func, "")

                self.result.setdefault(model_id, []).append(data)
                if model_id == "interface":
                    self.interfaces_data[data["inst_name"]] = data

        if self.is_topo:
            relationships = self.find_interface_relationships(topo_data)
            self.add_interface_assos(relationships)
            # 把接口的关联补充接口的关联关系中

    def add_interface_assos(self, relationships):
        for relationship in relationships:
            source_inst_name = relationship["source_inst_name"]
            if not self.interfaces_data.get(source_inst_name):
                continue
            data = {'asst_id': 'connect',
                    'inst_name': relationship["target_inst_name"],
                    'model_asst_id': 'interface_connect_interface',
                    'model_id': 'interface'
                    }
            self.interfaces_data.get(source_inst_name)["assos"].append(data)

    def find_interface_relationships(self, data):
        # 数据结构
        device_interfaces = defaultdict(dict)  # {instance_id: {ifindex: {"ifdescr": ..., "mac": ..., "ifalias": ...}}}
        ip_to_mac = defaultdict(dict)  # {instance_id: {ip: mac}}
        arp_table = defaultdict(dict)  # {instance_id: {ip: {"ifindex": ..., "mac": ...}}}

        # 预处理数据
        for entry in data:
            instance_id = entry['instance_id']
            tag = entry['tag']
            ifindex = entry.get('ifindex')
            value = entry.get('val')

            if tag == 'IFTable-IfDescr':  # 接口描述
                device_interfaces[instance_id].setdefault(ifindex, {})['ifdescr'] = value
            elif tag == 'IFTable-PhysAddress':  # 接口MAC地址
                device_interfaces[instance_id].setdefault(ifindex, {})['mac'] = self.normalize_mac(value)
            elif tag == 'IFTable-IfAlias':  # 接口别名
                device_interfaces[instance_id].setdefault(ifindex, {})['ifalias'] = value
            elif tag == 'IpAddr-IpAddr':  # IP地址与MAC地址的映射
                mac = device_interfaces[instance_id].get(ifindex, {}).get('mac')
                if mac:
                    ip_to_mac[instance_id][value] = mac
            elif tag == 'ARP-IfIndex':  # ARP表中的接口索引
                arp_table[instance_id].setdefault(ifindex, {})['ifindex'] = value
            elif tag == 'ARP-PhysAddress':  # ARP表中的MAC地址
                arp_table[instance_id].setdefault(ifindex, {})['mac'] = self.normalize_mac(value)

        # 构建 MAC 到设备和接口的索引
        mac_to_device = {}
        for instance_id, interfaces in device_interfaces.items():
            for ifindex, details in interfaces.items():
                mac = details.get('mac')
                if mac:
                    mac_to_device[mac] = (instance_id, ifindex)

        # 构建连接关系
        relations = []
        for src_instance, src_arp in arp_table.items():
            for ip, arp_info in src_arp.items():
                dst_mac = arp_info.get('mac')
                if not dst_mac:
                    continue

                # 使用索引快速查找目标设备和接口
                if dst_mac in mac_to_device:
                    dst_instance, dst_ifindex = mac_to_device[dst_mac]
                    if dst_instance == src_instance:
                        continue  # 跳过同一设备

                    if dst_instance not in self.instance_id_map or src_instance not in self.instance_id_map:
                        logger.info(
                            "This data is discarded because no feature library can be found for the OID. instance_id={}".format(
                                src_instance))
                        continue

                    src_ifindex = arp_info.get('ifindex')
                    src_interface = device_interfaces[src_instance].get(src_ifindex, {})
                    dst_interface = device_interfaces[dst_instance].get(dst_ifindex, {})
                    if not src_interface or not dst_interface:
                        continue

                    relations.append({
                        "source_device": src_instance,
                        # "source_interface": src_interface.get('ifalias') or src_interface.get('ifdescr'),
                        "source_inst_name": self.set_interface_inst_name(
                            data={"instance_id": src_instance, **self.set_alias_descr(src_interface)}),
                        "target_device": dst_instance,
                        # "target_interface": dst_interface.get('ifalias') or dst_interface.get('ifdescr'),
                        "target_inst_name": self.set_interface_inst_name(
                            data={"instance_id": dst_instance, **self.set_alias_descr(dst_interface)}),
                        "model_id": "interface",
                        "asst_id": "connect",
                        "model_asst_id": "interface_connect_interface",
                    })

        return relations

    @staticmethod
    def set_alias_descr(data):
        """设置别名"""
        result = {"description": data["ifdescr"]}
        if data.get("ifalias", ""):
            result["alias"] = data["ifalias"]

        return result

    @staticmethod
    def normalize_mac(mac):
        """将 MAC 地址标准化为统一格式"""
        if mac.startswith("0x"):
            mac = mac[2:]  # 去掉 "0x"
        return ":".join(mac[i:i + 2] for i in range(0, len(mac), 2)).lower()


class ProtocolCollectMetrics(CollectBase):
    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)

    @property
    def _metrics(self):
        data = PROTOCOL_METRIC_MAP[self.model_id]
        return data

    def prom_sql(self):
        sql = " or ".join(m for m in self._metrics)
        return sql

    @staticmethod
    def set_mysql_inst_name(data, *args, **kwargs):
        # {ip}-mysql-{port}
        inst_name = f"{data['ip_addr']}-mysql-{data['port']}"
        return inst_name

    @property
    def model_field_mapping(self):
        mapping = {
            "mysql": {
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "enable_binlog": "enable_binlog",
                "sync_binlog": "sync_binlog",
                "max_conn": "max_conn",
                "max_mem": "max_mem",
                "basedir": "basedir",
                "datadir": "datadir",
                "socket": "socket",
                "bind_address": "bind_address",
                "slow_query_log": "slow_query_log",
                "slow_query_log_file": "slow_query_log_file",
                "log_error": "log_error",
                "wait_timeout": "wait_timeout",
                "inst_name": self.set_mysql_inst_name
            },

        }

        return mapping

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
                **index_data["metric"],
            )

            self.collection_metrics_dict[metric_name].append(index_dict)

    def format_metrics(self):
        """格式化数据"""
        for metric_key, metrics in self.collection_metrics_dict.items():
            result = []
            mapping = self.model_field_mapping.get(self.model_id, {})
            for index_data in metrics:
                data = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data[key_or_func[1]])
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[self.model_id] = result


class AliyunCollectMetrics(CollectBase):
    _MODEL_ID = "aliyun_account"

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.model_resource_id_mapping = {}

    @property
    def _metrics(self):
        return ALIYUN_COLLECT_CLUSTER

    # def prom_sql(self):
    #     sql = " or ".join(
    #         "{}{{instance_id=\"{}\"}}".format(m, f"{self.task_id}_{self.inst_name}") for m in self._metrics)
    #     return sql

    def prom_sql(self):
        sql = " or ".join(m for m in self._metrics)
        return sql

    def check_task_id(self, instance_id):
        # 只要是同一个account 就认为是同一个task 为了保证不同的区域的数据能在同一个地方采集上来
        # TODO 做下架需要修改逻辑 保证task_id
        task_id, _ = instance_id.split("_", 1)
        return task_id == self.task_id

    @staticmethod
    def set_instance_inst_name(data, *args, **kwargs):
        # {resource_name}（{resource_id}）
        inst_name = f"{data['resource_name']}({data['resource_id']})"
        return inst_name

    def set_asso_instances(self, data, *args, **kwargs):
        model_id = kwargs["model_id"]
        result = [
            {
                "model_id": "aliyun_account",
                "inst_name": self.inst_name,
                "asst_id": "belong",
                "model_asst_id": f"{model_id}_belong_aliyun_account"
            }
        ]
        return result

    @property
    def model_field_mapping(self):
        mapping = {
            "aliyun_ecs": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "ip_addr": "ip_addr",
                "public_ip": "public_ip",
                "region": "region",
                "zone": "zone",
                "vpc": "vpc",
                "status": "status",
                "instance_type": "instance_type",
                "os_name": "os_name",
                "vcpus": (int, "vcpus"),
                "memory_mb": (int, "memory"),
                "charge_type": "charge_type",
                "create_time": (self.convert_datetime_format, "create_time"),
                "expired_time": (self.convert_datetime_format, "expired_time"),
                self.asso: self.set_asso_instances
            },
            "aliyun_bucket": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "location": "location",
                "extranet_endpoint": "extranet_endpoint",
                "intranet_endpoint": "intranet_endpoint",
                "storage_class": "storage_class",
                "cross_region_replication": "cross_region_replication",
                "block_public_access": "block_public_access",
                "creation_date": (self.convert_datetime_format, "creation_date"),
                self.asso: self.set_asso_instances

            },
            "aliyun_mysql": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "zone_slave": "zone_slave",
                "engine": "engine",
                "version": "version",
                "type": "type",
                "status": "status",
                "class": "class",
                "storage_type": "storage_type",
                "network_type": "network_type",
                "net_type": "net_type",
                "connection_mode": "connection_mode",
                "lock_mode": "lock_mode",
                "cpu": (int, "cpu"),
                "memory_mb": (int, "memory_mb"),
                "charge_type": "charge_type",
                "expire_time": (self.convert_datetime_format, "expire_time"),
                self.asso: self.set_asso_instances

            },
            "aliyun_pgsql": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "zone_slave": "zone_slave",
                "engine": "engine",
                "version": "version",
                "type": "type",
                "status": "status",
                "class": "class",
                "storage_type": "storage_type",
                "network_type": "network_type",
                "net_type": "net_type",
                "connection_mode": "connection_mode",
                "lock_mode": "lock_mode",
                "cpu": (int, "cpu"),
                "memory_mb": (int, "memory_mb"),
                "charge_type": "charge_type",
                "expire_time": (self.convert_datetime_format, "expire_time"),
                self.asso: self.set_asso_instances

            },
            "aliyun_mongodb": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "zone_slave": "zone_slave",
                "engine": "engine",
                "version": "version",
                "type": "type",
                "status": "status",
                "class": "class",
                "storage_type": "storage_type",
                "storage_gb": (int, "storage_gb"),
                "lock_mode": "lock_mode",
                "charge_type": "charge_type",
                "expire_time": (self.convert_datetime_format, "expire_time"),
                self.asso: self.set_asso_instances
            },
            "aliyun_redis": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "engine_version": "engine_version",
                "architecture_type": "architecture_type",
                "capacity": "capacity",
                "network_type": "network_type",
                "connection_domain": "connection_domain",
                "port": (int, "port"),
                "bandwidth": (int, "bandwidth"),
                "qps": (int, "qps"),
                "shard_count": "shard_count",
                "instance_class": "instance_class",
                "package_type": "package_type",
                "charge_type": "charge_type",
                "end_time": (self.convert_datetime_format, "end_time"),
                "create_time": (self.convert_datetime_format, "create_time"),
                self.asso: self.set_asso_instances
            },
            "aliyun_clb": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "zone_slave": "zone_slave",
                "vpc": "vpc",
                "ip_addr": "ip_addr",
                "status": "status",
                "class": "class",
                "charge_type": "charge_type",
                "create_time": (self.convert_datetime_format, "create_time"),
                self.asso: self.set_asso_instances
            },
            "aliyun_kafka_inst": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "vpc": "vpc",
                "status": "status",
                "class": "class",
                "storage_gb": (int, "storage_gb"),
                "storage_type": "storage_type",
                "msg_retain": (int, "msg_retain"),
                "topoc_num": (int, "topoc_num"),
                "io_max_read": (int, "io_max_read"),
                "io_max_write": (int, "io_max_write"),
                "charge_type": "charge_type",
                "create_time": (self.convert_datetime_format, "create_time"),
                self.asso: self.set_asso_instances
            }
        }

        return mapping

    def format_data(self, data):
        """格式化数据"""
        for index_data in data["result"]:
            metric_name = index_data["metric"]["__name__"]
            value = index_data["value"]
            instance_id = index_data["metric"]["instance_id"]
            if not self.check_task_id(instance_id):
                continue

            _time, value = value[0], value[1]
            if not self.timestamp_gt:
                if timestamp_gt_one_day_ago(_time):
                    break
                else:
                    self.timestamp_gt = True

            index_dict = dict(
                index_key=metric_name,
                index_value=value,
                **index_data["metric"],
            )

            self.collection_metrics_dict[metric_name].append(index_dict)

    def format_metrics(self):
        """格式化数据"""
        for metric_key, metrics in self.collection_metrics_dict.items():
            result = []
            model_id = metric_key.split("_info_gauge")[0]
            mapping = self.model_field_mapping.get(model_id, {})
            for index_data in metrics:
                data = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data[key_or_func[1]])
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data, model_id=model_id)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[model_id] = result


class HostCollectMetrics(CollectBase):
    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.os_type_list = [{"id": "1", "name": "Linux"}, {"id": "2", "name": "Windows"},
                             {"id": "3", "name": "AIX"},
                             {"id": "4", "name": "Unix"}, {"id": "other", "name": "Other"}]
        self.cup_arch_list = [{"id": "x86", "name": "x86"}, {"id": "x64", "name": "x64"}, {"id": "arm", "name": "ARM"},
                              {"id": "arm64", "name": "ARM64"}, {"id": "other", "name": "Other"}]

    @property
    def _metrics(self):
        data = HOST_COLLECT_METRIC
        return data

    def prom_sql(self):
        sql = " or ".join(
            "{}{{instance_id=\"{}\"}}".format(m, f"{self.task_id}_{self.inst_name}") for m in self._metrics)
        return sql

    @property
    def model_field_mapping(self):
        mapping = {
            "inst_name": self.set_inst_name,
            "hostname": "hostname",
            "os_type": self.set_os_type,
            "os_name": "os_name",
            "os_version": "os_version",
            "os_bit": "os_bits",
            "cpu_model": "cpu_model",
            "cpu_core": (self.transform_int, "cpu_cores"),
            "memory": (self.transform_int, "memory_gb"),
            "disk": (self.transform_int, "disk_gb"),
            "cpu_arch": self.set_cpu_arch,
            "inner_mac": (self.format_mac, "mac_address"),

        }

        return mapping

    def set_inst_name(self, *args, **kwargs):
        return self.inst_name

    @staticmethod
    def transform_int(data):
        return int(float(data))

    @staticmethod
    def format_mac(mac, *args, **kwargs):
        # 统一转为大写，冒号分隔
        mac = mac.strip().lower().replace("-", ":")
        if not re.match(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$", mac):
            return mac
        return mac.upper()

    def set_cpu_arch(self, data, *args, **kwargs):
        cpu_arch = data["cpu_architecture"]
        for arch in self.cup_arch_list:
            if arch["name"].lower() in cpu_arch.lower():
                return arch["id"]
        return "other"

    def set_os_type(self, data, *args, **kwargs):
        os_type = data["os_type"]
        for os in self.os_type_list:
            if os["name"].lower() in os_type.lower():
                return os["id"]
        return "other"

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
                **index_data["metric"],
            )

            self.collection_metrics_dict[metric_name].append(index_dict)

    def format_metrics(self):
        """格式化数据"""
        for metric_key, metrics in self.collection_metrics_dict.items():
            result = []
            for index_data in metrics:
                data = {}
                for field, key_or_func in self.model_field_mapping.items():
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data[key_or_func[1]])
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[self.model_id] = result


class MiddlewareCollectMetrics(CollectBase):
    @property
    def _metrics(self):
        assert self.model_id in MIDDLEWARE_METRIC_MAP, f"{self.model_id} needs to be defined in MIDDLEWARE_METRIC_MAP"
        return MIDDLEWARE_METRIC_MAP[self.model_id]

    def format_data(self, data):
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
                **index_data["metric"],
            )

            self.collection_metrics_dict[metric_name].append(index_dict)

    def get_inst_name(self, data):
        return f"{data['ip_addr']}-{self.model_id}-{data['port']}"

    @property
    def model_field_mapping(self):
        mapping = {
            "nginx": {
                "ip_addr": "ip_addr",
                # "port": lambda data: data["listen_port"].split("&"), # Multiple ports are separated by &
                "port": "port",
                "bin_path": "bin_path",
                "version": "version",
                "log_path": "log_path",
                "conf_path": "conf_path",
                "server_name": "server_name",
                "include": "include",
                "ssl_version": "ssl_version",
                "inst_name": self.get_inst_name
            },
            "zookeeper": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "install_path": "install_path",  # bin路径
                "log_path": "log_path",  # 运行日志路径
                "conf_path": "conf_path",  # 配置文件路径
                "java_path": "java_path",
                "java_version": "java_version",
                "data_dir": "data_dir",
                "tick_time": "tick_time",
                "init_limit": "init_limit",
                "sync_limit": "sync_limit",
                "server": "server"
            },
            "kafka": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "install_path": "install_path",  # bin路径
                "conf_path": "conf_path",  # 配置文件路径
                "log_path": "log_path",  # 运行日志路径
                "java_path": "java_path",
                "java_version": "java_version",
                "xms": "xms",  # 初始堆内存大小
                "xmx": "xmx",  # 最大堆内存大小
                "broker_id": "broker_id",  # broker id
                "io_threads": "io_threads",
                "network_threads": "network_threads",
                "socket_receive_buffer_bytes": "socket_receive_buffer_bytes",  # 接收缓冲区大小
                "socket_request_max_bytes": "socket_request_max_bytes",  # 单个请求套接字最大字节数
                "socket_send_buffer_bytes": "socket_send_buffer_bytes",  # 发送缓冲区大小
            },
            "etcd": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "data_dir": "data_dir",  # 快照文件路径
                "conf_file_path": "conf_file_path",
                "peer_port": "peer_port",  # 集群通讯端口
                "install_path": "install_path",
            },
            "rabbitmq": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "allport": "allport",
                "node_name": "node_name",
                "log_path": "log_path",
                "conf_path": "conf_path",
                "version": "version",
                "enabled_plugin_file": "enabled_plugin_file",
                "erlang_version": "erlang_version",
            },
            "tomcat": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "catalina_path": "catalina_path",
                "version": "version",
                "xms": "xms",
                "xmx": "xmx",
                "max_perm_size": "max_perm_size",
                "permsize": "permsize",
                "log_path": "log_path",
                "java_version": "java_version",
            },
            "apache":{
                "inst_name": self.get_inst_name,
                "ip_addr":"ip_addr",
                "port":"port",
                "version":"version",
                "httpd_path":"httpd_path",
                "httpd_conf_path":"httpd_conf_path",
                "doc_root":"doc_root",
                "error_log":"error_log",
                "custom_Log":"custom_Log",
                "include":"include",
            },
            "activemq":{
                "inst_name": self.get_inst_name,
                "ip_addr":"ip_addr",
                "port":"port",
                "version":"version",
                "install_path":"install_path",
                "conf_path":"conf_path",
                "java_path":"java_path",
                "java_version":"java_version",
                "xms":"xms",
                "xmx":"xmx",
            },
            "weblogic": {
                "inst_name": self.get_inst_name,
                "bk_obj_id": "bk_obj_id",
                "ip_addr": "ip_addr",
                "port": "port",
                "wlst_path": "wlst_path",
                "java_version": "java_version",
                "domain_version": "domain_version",
                "admin_server_name": "admin_server_name",
                "name": "name",
            },
            "keepalived": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "bk_obj_id": "bk_obj_id",
                "version": "version",
                "priority": "priority",
                "state": "state",
                "virtual_router_id": "virtual_router_id",
                "user_name": "user_name",
                "install_path": "install_path",
                "config_file": "config_file",
            },

        }

        return mapping

    def format_metrics(self):
        for metric_key, metrics in self.collection_metrics_dict.items():
            result = []
            mapping = self.model_field_mapping.get(self.model_id, {})
            for index_data in metrics:
                data = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data[key_or_func[1]])
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[self.model_id] = result

    def prom_sql(self):
        sql = " or ".join(m for m in self._metrics)
        return sql


class QCloudCollectMetrics(CollectBase):
    _MODEL_ID = "qcloud"

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.model_resource_id_mapping = {}

    @property
    def _metrics(self):
        return QCLOUD_COLLECT_CLUSTER

    def prom_sql(self):
        sql = " or ".join(m for m in self._metrics)
        return sql

    @staticmethod
    def set_instance_inst_name(data, *args, **kwargs):
        if not data.get("resource_name"):
            print(data)
        inst_name = f"{data['resource_name']}_{data['resource_id']}"
        return inst_name

    def set_asso_instances(self, data, *args, **kwargs):
        model_id = kwargs["model_id"]
        result = [
            {
                "model_id": "qcloud",
                "inst_name": self.inst_name,
                "asst_id": "belong",
                "model_asst_id": f"{model_id}_belong_{self._MODEL_ID}"
            }
        ]
        return result

    @property
    def model_field_mapping(self):

        mapping = {
            "qcloud_cvm": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "ip_addr": "ip_addr",
                "public_ip": "public_ip",
                "region": "region",
                "zone": "zone",
                "vpc": "vpc",
                "status": "status",
                "instance_type": "instance_type",
                "os_name": "os_name",
                "vcpus": (int, "vcpus"),
                "memory_mb": (int, "memory_mb"),
                "charge_type": "charge_type",
            },
            "qcloud_rocketmq": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "status": "status",
                "topic_num": (int, "topic_num"),
                "used_topic_num": (int, "used_topic_num"),
                "tpsper_name_space": (int, "tpsper_name_space"),
                "name_space_num": (int, "name_space_num"),
                "group_num": (int, "group_num"),
            },
            "qcloud_mysql": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "ip_addr": "ip_addr",
                "region": "region",
                "zone": "zone",
                "status": "status",
                "volume": (int, "volume"),
                "memory_mb": (int, "memory_mb"),
                "charge_type": "charge_type",
            },
            "qcloud_redis": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "ip_addr": "ip_addr",
                "vpc": "vpc",
                "region": "region",
                "zone": "zone",
                "port": "port",
                "wan_address": "wan_address",
                "status": "status",
                "sub_status": "sub_status",
                "engine": "engine",
                "version": "version",
                "type": "type",
                "memory_mb": "memory_mb",
                "shard_size": "shard_size",
                "shard_num": "shard_num",
                "replicas_num": "replicas_num",
                "client_limit": "client_limit",
                "net_limit": "net_limit",
                "charge_type": "charge_type",
            },
            "qcloud_mongodb": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "ip_addr": "ip_addr",
                "tag": "tag",
                "project_id": "project_id",
                "vpc": "vpc",
                "region": "region",
                "zone": "zone",
                "port": "port",
                "status": "status",
                "cluster_type": "cluster_type",
                "machine_type": "machine_type",
                "version": "version",
                "cpu": "cpu",
                "memory_mb": "memory_mb",
                "volume_mb": "volume_mb",
                "secondary_num": "secondary_num",
                "mongos_cpu": "mongos_cpu",
                "mongos_memory_mb": "mongos_memory_mb",
                "mongos_node_num": "mongos_node_num",
                "charge_type": "charge_type",

            },
            "qcloud_pgsql": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tag": "tag",
                "project_id": "project_id",
                "vpc": "vpc",
                "region": "region",
                "zone": "zone",
                "status": "status",
                "chartset": "chartset",
                "engine": "engine",
                "mode": "mode",
                "version": "version",
                "kernel_version": "kernel_version",
                "cpu": "cpu",
                "memory_mb": "memory_mb",
                "volume_mb": "volume_mb",
                "charge_type": "charge_type",
            },
            "qcloud_pulsar_cluster": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tag": "tag",
                "project_id": "project_id",
                "region": "region",
                "status": "status",
                "version": "version",
                "vpc_endpoint": "vpc_endpoint",
                "public_endpoint": "public_endpoint",
                "max_namespace_num": "max_namespace_num",
                "max_topic_num": "max_topic_num",
                "max_qps": "max_qps",
                "max_retention_s": "max_retention_s",
                "max_storage_mb": "max_storage_mb",
                "max_delay_s": "max_delay_s",
                "charge_type": "charge_type",
            },
            "qcloud_cmq": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tag": "tag",
                "region": "region",
                "status": "status",
                "max_delay_s": "max_delay_s",
                "polling_wait_s": "polling_wait_s",
                "visibility_timeout_s": "visibility_timeout_s",
                "max_message_b": "max_message_b",
                "qps": "qps",
            },
            "qcloud_cmq_topic": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tag": "tag",
                "region": "region",
                "status": "status",
                "max_retention_s": "max_retention_s",
                "max_message_b": "max_message_b",
                "filter_type": "filter_type",
                "qps": "qps",
            },
            "qcloud_clb": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tag": "tag",
                "project_id": "project_id",
                "security_group_id": "security_group_id",
                "vpc": "vpc",
                "region": "region",
                "master_zone": "master_zone",
                "backup_zone": "backup_zone",
                "status": "status",
                "domain": "domain",
                "ip_addr": "ip_addr",
                "type": "type",
                "isp": "isp",
                "charge_type": "charge_type",
            },
            "qcloud_eip": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tag": "tag",
                "region": "region",
                "status": "status",
                "type": "type",
                "ip_addr": "ip_addr",
                "instance_type": "instance_type",
                "instance_id": "instance_id",
                "isp": "isp",
                "charge_type": "charge_type",

            },
            "qcloud_bucket": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
            },
            "qcloud_filesystem": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tag": "tag",
                "region": "region",
                "zone": "zone",
                "status": "status",
                "protocol": "protocol",
                "type": "type",
                "net_limit": (int, "net_limit"),
                "size_gib": (int, "size_gib"),
            },
            "qcloud_domain": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tld": "tld",
                "status": "status",
            }
        }
        return mapping

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
                **index_data["metric"],
            )

            self.collection_metrics_dict[metric_name].append(index_dict)

    def format_metrics(self):
        """格式化数据"""
        for metric_key, metrics in self.collection_metrics_dict.items():
            result = []
            model_id = metric_key.split("_info_gauge")[0]
            mapping = self.model_field_mapping.get(model_id, {})
            for index_data in metrics:
                data = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data[key_or_func[1]])
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data, model_id=model_id)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[model_id] = result


class DBCollectCollectMetrics(CollectBase):
    """数据库 采集指标"""

    @property
    def _metrics(self):
        assert self.model_id in DB_COLLECT_METRIC_MAP, f"{self.model_id} needs to be defined in DB_COLLECT_METRIC_MAP"
        return DB_COLLECT_METRIC_MAP[self.model_id]

    def format_data(self, data):
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
                **index_data["metric"],
            )

            self.collection_metrics_dict[metric_name].append(index_dict)

    def get_inst_name(self, data):
        return f"{data['ip_addr']}-{self.model_id}-{data['port']}"

    @property
    def model_field_mapping(self):

        mapping = {
            "es": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "log_path": "log_path",
                "data_path": "data_path",
                "is_master": "is_master",
                "node_name": "node_name",
                "cluster_name": "cluster_name",
                "java_version": "java_version",
                "java_path": "java_path",
                "conf_path": "conf_path",
                "install_path": "install_path",
            },
            "redis": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "install_path": "install_path",
                "max_conn": "max_conn",
                "max_mem": "max_mem",
                "database_role": "database_role",
            },
            "mongodb":{
                "inst_name": self.get_inst_name,
                "ip_addr":"ip_addr",
                "port":"port",
                "version":"version",
                "mongo_path":"mongo_path",
                "bin_path":"bin_path",
                "config":"config",
                "fork":"fork",
                "system_log":"system_log",
                "db_path":"db_path",
                "max_incoming_conn":"max_incoming_conn",
                "database_role":"database_role",
            },
            "postgresql":{
                "inst_name": lambda x: f"{x['ip_addr']}-pg-{x['port']}",
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "conf_path": "conf_path",
                "data_path": "data_path",
                "max_conn": "max_conn",
                "cache_memory_mb": "cache_memory_mb",
                "log_path": "log_path",
            }
        }
        return mapping

    def format_metrics(self):
        for metric_key, metrics in self.collection_metrics_dict.items():
            result = []
            mapping = self.model_field_mapping.get(self.model_id, {})
            for index_data in metrics:
                data = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data[key_or_func[1]])
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[self.model_id] = result

    def prom_sql(self):
        sql = " or ".join(m for m in self._metrics)
        return sql
