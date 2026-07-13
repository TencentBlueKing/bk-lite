from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from rest_framework.exceptions import ValidationError

from apps.cmdb.services.instance import InstanceManage


MODEL_CLUSTER = "k8s_cluster"
MODEL_NAMESPACE = "k8s_namespace"
MODEL_WORKLOAD = "k8s_workload"
MODEL_POD = "k8s_pod"
MODEL_NODE = "k8s_node"

BUSINESS_WORKLOAD_KINDS = ("deployment", "statefulset", "daemonset", "job", "cronjob")
RESOURCE_KINDS = ("namespace", *BUSINESS_WORKLOAD_KINDS, "other_workload", "pod", "node")
LAYER_LIMITS = {"namespace": 20, "workload": 50, "node": 50}


def _id(instance: dict) -> int | None:
    try:
        return int(instance.get("_id"))
    except (TypeError, ValueError):
        return None


def _name(instance: dict) -> str:
    return str(instance.get("name") or instance.get("inst_name") or instance.get("_id") or "")


def _workload_type(instance: dict) -> str:
    value = instance.get("workload_type")
    if isinstance(value, (list, tuple, set)):
        value = next((item for item in value if item not in (None, "")), "")
    return str(value or "").strip().casefold()


def _dedupe(instances: list[dict]) -> list[dict]:
    result: dict[int, dict] = {}
    for instance in instances:
        inst_id = _id(instance)
        if inst_id is not None:
            result.setdefault(inst_id, instance)
    return list(result.values())


@dataclass
class K8sSnapshot:
    cluster: dict
    namespaces: dict[int, dict]
    workloads: dict[int, dict]
    pods: dict[int, dict]
    nodes: dict[int, dict]
    all_nodes: dict[int, dict]
    namespace_workloads: dict[int, list[int]]
    namespace_direct_pods: dict[int, list[int]]
    workload_pods: dict[int, list[int]]
    workload_namespace: dict[int, int]
    pod_namespace: dict[int, int]
    pod_workload: dict[int, int]


class K8sResourceOverviewService:
    @staticmethod
    def _associated_instances(associations: list[dict], model_id: str) -> list[dict]:
        result = []
        for association in associations or []:
            association_models = {
                association.get("src_model_id"),
                association.get("dst_model_id"),
            }
            for instance in association.get("inst_list") or []:
                instance_model_id = instance.get("model_id")
                if instance_model_id == model_id:
                    result.append(instance)
                elif instance_model_id is None and model_id in association_models:
                    # Graph 关联查询返回的实体不保证包含 model_id；关联组的端点模型
                    # 是可靠来源。复制后补齐，避免污染底层查询对象和其他遍历。
                    result.append({**instance, "model_id": model_id})
        return _dedupe(result)

    @staticmethod
    def _filter_visible(instances, model_id, permission_maps=None, user=None) -> list[dict]:
        permission_map = (permission_maps or {}).get(model_id)
        return [
            instance
            for instance in _dedupe(list(instances))
            if InstanceManage._has_topology_view_permission(instance, permission_map, user=user)
        ]

    @classmethod
    def build_snapshot(cls, cluster_id: int, permission_maps=None, user=None) -> K8sSnapshot:
        cluster = InstanceManage.query_entity_by_id(int(cluster_id))
        if not cluster:
            raise ValidationError("实例不存在")
        if cluster.get("model_id") != MODEL_CLUSTER:
            raise ValidationError("实例不是 k8s_cluster")

        cluster_associations = InstanceManage.instance_association_instance_list(MODEL_CLUSTER, int(cluster_id)) or []
        raw_namespaces = cls._associated_instances(cluster_associations, MODEL_NAMESPACE)
        raw_nodes = cls._associated_instances(cluster_associations, MODEL_NODE)
        namespaces = {
            _id(item): item
            for item in cls._filter_visible(raw_namespaces, MODEL_NAMESPACE, permission_maps, user)
            if _id(item) is not None
        }
        nodes = {
            _id(item): item
            for item in cls._filter_visible(raw_nodes, MODEL_NODE, permission_maps, user)
            if _id(item) is not None
        }
        all_nodes = {_id(item): item for item in raw_nodes if _id(item) is not None}

        workloads: dict[int, dict] = {}
        pods: dict[int, dict] = {}
        namespace_workloads: dict[int, list[int]] = defaultdict(list)
        namespace_direct_pods: dict[int, list[int]] = defaultdict(list)
        workload_pods: dict[int, list[int]] = defaultdict(list)
        workload_namespace: dict[int, int] = {}
        pod_namespace: dict[int, int] = {}
        pod_workload: dict[int, int] = {}

        for namespace_id, namespace in namespaces.items():
            associations = InstanceManage.instance_association_instance_list(MODEL_NAMESPACE, namespace_id) or []
            visible_workloads = cls._filter_visible(
                cls._associated_instances(associations, MODEL_WORKLOAD), MODEL_WORKLOAD, permission_maps, user
            )
            for workload in visible_workloads:
                workload_id = _id(workload)
                if workload_id is None:
                    continue
                workloads[workload_id] = workload
                workload_namespace[workload_id] = namespace_id
                if workload_id not in namespace_workloads[namespace_id]:
                    namespace_workloads[namespace_id].append(workload_id)

            direct_pods = cls._filter_visible(
                cls._associated_instances(associations, MODEL_POD), MODEL_POD, permission_maps, user
            )
            for pod in direct_pods:
                pod_id = _id(pod)
                if pod_id is None:
                    continue
                pods[pod_id] = pod
                pod_namespace[pod_id] = namespace_id
                if pod_id not in namespace_direct_pods[namespace_id]:
                    namespace_direct_pods[namespace_id].append(pod_id)

        for workload_id, workload in list(workloads.items()):
            associations = InstanceManage.instance_association_instance_list(MODEL_WORKLOAD, workload_id) or []
            visible_pods = cls._filter_visible(
                cls._associated_instances(associations, MODEL_POD), MODEL_POD, permission_maps, user
            )
            namespace_id = workload_namespace[workload_id]
            for pod in visible_pods:
                pod_id = _id(pod)
                if pod_id is None:
                    continue
                pods[pod_id] = pod
                pod_namespace[pod_id] = namespace_id
                pod_workload[pod_id] = workload_id
                if pod_id not in workload_pods[workload_id]:
                    workload_pods[workload_id].append(pod_id)
                if pod_id in namespace_direct_pods[namespace_id]:
                    namespace_direct_pods[namespace_id].remove(pod_id)

        return K8sSnapshot(
            cluster=cluster,
            namespaces=namespaces,
            workloads=workloads,
            pods=pods,
            nodes=nodes,
            all_nodes=all_nodes,
            namespace_workloads=dict(namespace_workloads),
            namespace_direct_pods=dict(namespace_direct_pods),
            workload_pods=dict(workload_pods),
            workload_namespace=workload_namespace,
            pod_namespace=pod_namespace,
            pod_workload=pod_workload,
        )

    @staticmethod
    def _node(instance: dict, layer: str, **extra) -> dict:
        return {
            "id": str(instance.get("_id")),
            "model_id": instance.get("model_id", ""),
            "name": _name(instance),
            "layer": layer,
            **extra,
        }

    @staticmethod
    def _edge(source, target, kind: str) -> dict:
        return {"id": f"{kind}:{source}:{target}", "source": str(source), "target": str(target), "kind": kind}

    @staticmethod
    def _collection_facts(cluster: dict) -> dict:
        return {
            "last_reported_at": cluster.get("last_reported_at") or cluster.get("reported_at"),
            "last_success_at": cluster.get("last_success_at") or cluster.get("last_collected_at"),
            "last_error": cluster.get("last_error") or cluster.get("collection_error"),
            "collector_task": cluster.get("collector_task"),
        }

    @classmethod
    def get_overview(cls, cluster_id: int, permission_maps=None, user=None) -> dict:
        snapshot = cls.build_snapshot(cluster_id, permission_maps=permission_maps, user=user)
        sorted_namespaces = sorted(snapshot.namespaces.values(), key=lambda item: (_name(item).casefold(), _id(item)))
        shown_namespaces = sorted_namespaces[: LAYER_LIMITS["namespace"]]
        shown_namespace_ids = {_id(item) for item in shown_namespaces}

        eligible_workloads = [
            workload
            for workload_id, workload in snapshot.workloads.items()
            if snapshot.workload_namespace.get(workload_id) in shown_namespace_ids
        ]
        eligible_workloads.sort(
            key=lambda item: (
                _name(snapshot.namespaces[snapshot.workload_namespace[_id(item)]]).casefold(),
                _workload_type(item),
                _name(item).casefold(),
                _id(item),
            )
        )
        shown_workloads = eligible_workloads[: LAYER_LIMITS["workload"]]
        sorted_nodes = sorted(snapshot.nodes.values(), key=lambda item: (_name(item).casefold(), _id(item)))
        shown_nodes = sorted_nodes[: LAYER_LIMITS["node"]]

        topology_nodes = [cls._node(snapshot.cluster, "cluster")]
        topology_nodes.extend(cls._node(item, "namespace") for item in shown_namespaces)
        topology_nodes.extend(
            cls._node(
                item,
                "workload",
                workload_type=_workload_type(item),
                pod_count=len(snapshot.workload_pods.get(_id(item), [])),
            )
            for item in shown_workloads
        )
        topology_nodes.extend(cls._node(item, "node") for item in shown_nodes)

        cluster_node_id = _id(snapshot.cluster)
        topology_edges = [cls._edge(cluster_node_id, _id(item), "cluster-namespace") for item in shown_namespaces]
        topology_edges.extend(
            cls._edge(snapshot.workload_namespace[_id(item)], _id(item), "namespace-workload")
            for item in shown_workloads
        )
        topology_edges.extend(cls._edge(cluster_node_id, _id(item), "cluster-node") for item in shown_nodes)

        business_count = sum(
            1 for item in snapshot.workloads.values() if _workload_type(item) in BUSINESS_WORKLOAD_KINDS
        )
        return {
            "summary": {
                "namespace_count": len(snapshot.namespaces),
                "workload_count": business_count,
                "other_workload_count": len(snapshot.workloads) - business_count,
                "pod_count": len(snapshot.pods),
                "node_count": len(snapshot.nodes),
            },
            "collection_facts": cls._collection_facts(snapshot.cluster),
            "topology": {"nodes": topology_nodes, "edges": topology_edges},
            "layers": {
                "namespace": {"shown": len(shown_namespaces), "count": len(snapshot.namespaces), "page_size": 20},
                "workload": {"shown": len(shown_workloads), "count": len(eligible_workloads), "page_size": 50},
                "node": {"shown": len(shown_nodes), "count": len(snapshot.nodes), "page_size": 50},
            },
        }

    @classmethod
    def _pod_node_relation(cls, snapshot: K8sSnapshot, pod: dict, permission_maps=None, user=None):
        pod_id = _id(pod)
        associations = InstanceManage.instance_association_instance_list(MODEL_POD, pod_id) or []
        related_nodes = cls._associated_instances(associations, MODEL_NODE)
        if related_nodes:
            target = related_nodes[0]
            target_id = _id(target)
            if target_id in snapshot.nodes:
                return cls._node(snapshot.nodes[target_id], "node"), target_id
            if target_id in snapshot.all_nodes:
                return {
                    "id": "virtual:node-forbidden",
                    "model_id": "virtual",
                    "name": "目标 Node 无权限",
                    "layer": "node",
                }, "virtual:node-forbidden"
            return {
                "id": "virtual:node-unmatched",
                "model_id": "virtual",
                "name": "Node 未匹配",
                "layer": "node",
            }, "virtual:node-unmatched"
        if pod.get("node"):
            return {
                "id": "virtual:node-unmatched",
                "model_id": "virtual",
                "name": "Node 未匹配",
                "layer": "node",
            }, "virtual:node-unmatched"
        return {
            "id": "virtual:unscheduled",
            "model_id": "virtual",
            "name": "未调度",
            "layer": "node",
        }, "virtual:unscheduled"

    @classmethod
    def _pod_branch(cls, snapshot, pod_ids, parent_id, parent_kind, permission_maps=None, user=None):
        nodes = []
        edges = []
        seen_nodes = set()
        for pod_id in pod_ids:
            pod = snapshot.pods[pod_id]
            nodes.append(cls._node(pod, "pod"))
            edges.append(cls._edge(parent_id, pod_id, parent_kind))
            node, target_id = cls._pod_node_relation(snapshot, pod, permission_maps, user)
            if node["model_id"] == "virtual" and node["id"] not in seen_nodes:
                seen_nodes.add(node["id"])
                nodes.append(node)
            edges.append(cls._edge(pod_id, target_id, "pod-node"))
        return nodes, edges

    @classmethod
    def get_workload_pods(cls, cluster_id, workload_id, page=1, page_size=50, permission_maps=None, user=None):
        snapshot = cls.build_snapshot(cluster_id, permission_maps=permission_maps, user=user)
        workload_id = int(workload_id)
        if workload_id not in snapshot.workloads:
            raise ValidationError("Workload 不属于当前集群或无权限")
        pod_ids = sorted(snapshot.workload_pods.get(workload_id, []), key=lambda item: (_name(snapshot.pods[item]).casefold(), item))
        count = len(pod_ids)
        start = (int(page) - 1) * int(page_size)
        current_ids = pod_ids[start: start + int(page_size)]
        nodes, edges = cls._pod_branch(snapshot, current_ids, workload_id, "workload-pod", permission_maps, user)
        return {"nodes": nodes, "edges": edges, "count": count, "page": int(page), "page_size": int(page_size)}

    @classmethod
    def get_unowned_pods(cls, cluster_id, page=1, page_size=50, permission_maps=None, user=None):
        snapshot = cls.build_snapshot(cluster_id, permission_maps=permission_maps, user=user)
        pod_ids = sorted(
            [pod_id for ids in snapshot.namespace_direct_pods.values() for pod_id in ids],
            key=lambda item: (_name(snapshot.pods[item]).casefold(), item),
        )
        count = len(pod_ids)
        start = (int(page) - 1) * int(page_size)
        current_ids = pod_ids[start: start + int(page_size)]
        nodes = []
        edges = []
        for namespace_id, namespace_pods in snapshot.namespace_direct_pods.items():
            selected = [pod_id for pod_id in current_ids if pod_id in namespace_pods]
            branch_nodes, branch_edges = cls._pod_branch(
                snapshot, selected, namespace_id, "namespace-pod", permission_maps, user
            )
            nodes.extend(branch_nodes)
            edges.extend(branch_edges)
        unique_nodes = {node["id"]: node for node in nodes}
        return {"nodes": list(unique_nodes.values()), "edges": edges, "count": count, "page": int(page), "page_size": int(page_size)}

    @classmethod
    def list_resources(
        cls,
        cluster_id,
        kind,
        page=1,
        page_size=20,
        search="",
        order="name",
        namespace_id=None,
        workload_id=None,
        node_id=None,
        permission_maps=None,
        user=None,
    ):
        if kind not in RESOURCE_KINDS:
            raise ValidationError(f"不支持的资源类型: {kind}")
        snapshot = cls.build_snapshot(cluster_id, permission_maps=permission_maps, user=user)
        if namespace_id is not None and int(namespace_id) not in snapshot.namespaces:
            raise ValidationError("Namespace 不属于当前集群或无权限")
        if workload_id is not None and int(workload_id) not in snapshot.workloads:
            raise ValidationError("Workload 不属于当前集群或无权限")
        if node_id is not None and int(node_id) not in snapshot.nodes:
            raise ValidationError("Node 不属于当前集群或无权限")

        items: list[dict[str, Any]] = []
        if kind == "namespace":
            for item_id, item in snapshot.namespaces.items():
                workload_ids = snapshot.namespace_workloads.get(item_id, [])
                pod_ids = set(snapshot.namespace_direct_pods.get(item_id, []))
                for workload in workload_ids:
                    pod_ids.update(snapshot.workload_pods.get(workload, []))
                items.append({"id": str(item_id), "name": _name(item), "workload_count": len(workload_ids), "pod_count": len(pod_ids)})
        elif kind in BUSINESS_WORKLOAD_KINDS or kind == "other_workload":
            for item_id, item in snapshot.workloads.items():
                item_kind = _workload_type(item)
                if kind == "other_workload" and item_kind in BUSINESS_WORKLOAD_KINDS:
                    continue
                if kind != "other_workload" and item_kind != kind:
                    continue
                ns_id = snapshot.workload_namespace[item_id]
                if namespace_id is not None and ns_id != int(namespace_id):
                    continue
                items.append({
                    "id": str(item_id),
                    "name": _name(item),
                    "namespace": _name(snapshot.namespaces[ns_id]),
                    "namespace_id": str(ns_id),
                    "workload_type": item_kind,
                    "replicas": item.get("replicas"),
                    "pod_count": len(snapshot.workload_pods.get(item_id, [])),
                })
        elif kind == "pod":
            for item_id, item in snapshot.pods.items():
                ns_id = snapshot.pod_namespace.get(item_id)
                owner_id = snapshot.pod_workload.get(item_id)
                if namespace_id is not None and ns_id != int(namespace_id):
                    continue
                if workload_id is not None and owner_id != int(workload_id):
                    continue
                if node_id is not None:
                    related_node, related_id = cls._pod_node_relation(snapshot, item, permission_maps, user)
                    if related_id != int(node_id):
                        continue
                items.append({
                    "id": str(item_id),
                    "name": _name(item),
                    "namespace": _name(snapshot.namespaces[ns_id]) if ns_id in snapshot.namespaces else None,
                    "namespace_id": str(ns_id) if ns_id is not None else None,
                    "workload": _name(snapshot.workloads[owner_id]) if owner_id in snapshot.workloads else None,
                    "workload_id": str(owner_id) if owner_id is not None else None,
                    "node": item.get("node"),
                    "ip_addr": item.get("ip_addr"),
                    "request_cpu": item.get("request_cpu"),
                    "request_memory": item.get("request_memory"),
                    "limit_cpu": item.get("limit_cpu"),
                    "limit_memory": item.get("limit_memory"),
                })
        else:
            for item_id, item in snapshot.nodes.items():
                items.append({
                    "id": str(item_id),
                    "name": _name(item),
                    "role": item.get("role"),
                    "cpu": item.get("cpu"),
                    "memory": item.get("memory"),
                    "disk": item.get("disk"),
                })

        if search:
            needle = str(search).casefold()
            items = [item for item in items if needle in str(item.get("name") or "").casefold()]
        reverse = str(order).startswith("-")
        order_key = str(order).removeprefix("-") or "name"
        items.sort(key=lambda item: (str(item.get(order_key) or "").casefold(), str(item.get("id"))), reverse=reverse)
        count = len(items)
        start = (int(page) - 1) * int(page_size)
        return {"items": items[start: start + int(page_size)], "count": count, "page": int(page), "page_size": int(page_size)}

    @classmethod
    def get_layer(
        cls,
        cluster_id,
        layer,
        page=1,
        page_size=None,
        namespace_ids=None,
        permission_maps=None,
        user=None,
    ):
        if layer not in LAYER_LIMITS:
            raise ValidationError(f"不支持的拓扑层: {layer}")
        snapshot = cls.build_snapshot(cluster_id, permission_maps=permission_maps, user=user)
        page_size = int(page_size or LAYER_LIMITS[layer])
        if page_size > LAYER_LIMITS[layer]:
            raise ValidationError(f"{layer} page_size 不能超过 {LAYER_LIMITS[layer]}")

        if layer == "namespace":
            items = sorted(snapshot.namespaces.values(), key=lambda item: (_name(item).casefold(), _id(item)))
            parent = _id(snapshot.cluster)
            edge_kind = "cluster-namespace"
        elif layer == "node":
            items = sorted(snapshot.nodes.values(), key=lambda item: (_name(item).casefold(), _id(item)))
            parent = _id(snapshot.cluster)
            edge_kind = "cluster-node"
        else:
            normalized_namespace_ids = {int(item) for item in (namespace_ids or [])}
            if not normalized_namespace_ids or not normalized_namespace_ids.issubset(snapshot.namespaces.keys()):
                raise ValidationError("Workload 分层查询必须提供当前集群内已加载的 Namespace")
            items = [
                item
                for item_id, item in snapshot.workloads.items()
                if snapshot.workload_namespace[item_id] in normalized_namespace_ids
            ]
            items.sort(
                key=lambda item: (
                    _name(snapshot.namespaces[snapshot.workload_namespace[_id(item)]]).casefold(),
                    _workload_type(item),
                    _name(item).casefold(),
                    _id(item),
                )
            )
            parent = None
            edge_kind = "namespace-workload"

        count = len(items)
        start = (int(page) - 1) * page_size
        selected = items[start: start + page_size]
        nodes = [cls._node(item, layer) for item in selected]
        edges = [
            cls._edge(
                snapshot.workload_namespace[_id(item)] if layer == "workload" else parent,
                _id(item),
                edge_kind,
            )
            for item in selected
        ]
        return {"nodes": nodes, "edges": edges, "count": count, "page": int(page), "page_size": page_size}
