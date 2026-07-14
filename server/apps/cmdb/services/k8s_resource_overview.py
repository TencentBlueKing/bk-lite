from __future__ import annotations

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


class K8sResourceOverviewService:
    PERMISSION_SCAN_PAGE_SIZE = 500

    @staticmethod
    def _query_page(model_id, inst_ids, *, permission_maps=None, user=None, **kwargs):
        return InstanceManage.query_entity_page_by_ids(
            inst_ids,
            permission_map=(permission_maps or {}).get(model_id),
            creator=getattr(user, "username", "") if user is not None else "",
            **kwargs,
        )

    @staticmethod
    def _count_ids(model_id, inst_ids, *, permission_maps=None, user=None, filters=None):
        return InstanceManage.count_entity_by_ids(
            inst_ids,
            permission_map=(permission_maps or {}).get(model_id),
            creator=getattr(user, "username", "") if user is not None else "",
            filters=filters,
        )

    @classmethod
    def _visible_candidate_ids(cls, model_id, inst_ids, *, permission_maps=None, user=None):
        """分批收敛父资源候选，避免可见子资源绕过不可见父资源。"""
        candidate_ids = sorted({int(inst_id) for inst_id in inst_ids})
        if not (permission_maps or {}).get(model_id):
            return candidate_ids

        visible_ids = []
        page = 1
        while True:
            rows, count = cls._query_page(
                model_id,
                candidate_ids,
                page=page,
                page_size=cls.PERMISSION_SCAN_PAGE_SIZE,
                order="name",
                permission_maps=permission_maps,
                user=user,
            )
            visible_ids.extend(_id(row) for row in rows if _id(row) is not None)
            if len(visible_ids) >= count or not rows:
                break
            page += 1
        return visible_ids

    @staticmethod
    def _relation_ids(relation_map: dict[int, list[int]]) -> list[int]:
        return sorted({related_id for related_ids in relation_map.values() for related_id in related_ids})

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
        return cls._get_overview_batched(
            cluster_id, permission_maps=permission_maps, user=user
        )

    @classmethod
    def _get_overview_batched(cls, cluster_id: int, permission_maps=None, user=None) -> dict:
        """用固定次数的批量关系查询构建默认概览，不读取 Pod 实体。"""
        cluster = InstanceManage.query_entity_by_id(int(cluster_id))
        if not cluster:
            raise ValidationError("实例不存在")
        if cluster.get("model_id") != MODEL_CLUSTER:
            raise ValidationError("实例不是 k8s_cluster")

        namespace_map = InstanceManage.instance_association_map(MODEL_CLUSTER, [cluster_id], MODEL_NAMESPACE)
        node_map = InstanceManage.instance_association_map(MODEL_CLUSTER, [cluster_id], MODEL_NODE)
        namespace_ids = cls._visible_candidate_ids(
            MODEL_NAMESPACE,
            cls._relation_ids(namespace_map),
            permission_maps=permission_maps,
            user=user,
        )
        node_ids = cls._relation_ids(node_map)
        namespaces, namespace_count = cls._query_page(
            MODEL_NAMESPACE, namespace_ids, page_size=LAYER_LIMITS["namespace"], order="name",
            permission_maps=permission_maps, user=user,
        )
        nodes, node_count = cls._query_page(
            MODEL_NODE, node_ids, page_size=LAYER_LIMITS["node"], order="name",
            permission_maps=permission_maps, user=user,
        )

        workload_map = InstanceManage.instance_association_map(MODEL_NAMESPACE, namespace_ids, MODEL_WORKLOAD)
        workload_namespace = {
            workload_id: namespace_id
            for namespace_id, related_ids in workload_map.items()
            for workload_id in related_ids
        }
        shown_namespace_ids = {_id(item) for item in namespaces}
        shown_workload_ids = cls._relation_ids(
            {namespace_id: ids for namespace_id, ids in workload_map.items() if namespace_id in shown_namespace_ids}
        )
        workloads, shown_workload_count = cls._query_page(
            MODEL_WORKLOAD, shown_workload_ids, page_size=LAYER_LIMITS["workload"], order="name",
            permission_maps=permission_maps, user=user,
        )
        workload_ids = cls._relation_ids(workload_map)
        pod_map = InstanceManage.instance_association_map(MODEL_WORKLOAD, workload_ids, MODEL_POD)
        direct_pod_map = InstanceManage.instance_association_map(
            MODEL_NAMESPACE, namespace_ids, MODEL_POD
        )
        pod_ids = set(cls._relation_ids(pod_map)) | set(cls._relation_ids(direct_pod_map))
        pod_count = cls._count_ids(MODEL_POD, pod_ids, permission_maps=permission_maps, user=user)

        namespace_by_id = {_id(item): item for item in namespaces}
        topology_nodes = [cls._node(cluster, "cluster")]
        topology_nodes.extend(cls._node(item, "namespace") for item in namespaces)
        topology_nodes.extend(
            cls._node(item, "workload", workload_type=_workload_type(item), pod_count=len(pod_map.get(_id(item), [])))
            for item in workloads
        )
        topology_nodes.extend(cls._node(item, "node") for item in nodes)

        cluster_node_id = _id(cluster)
        topology_edges = [cls._edge(cluster_node_id, _id(item), "cluster-namespace") for item in namespaces]
        topology_edges.extend(
            cls._edge(workload_namespace[_id(item)], _id(item), "namespace-workload")
            for item in workloads
            if workload_namespace.get(_id(item)) in namespace_by_id
        )
        topology_edges.extend(cls._edge(cluster_node_id, _id(item), "cluster-node") for item in nodes)

        business_count = cls._count_ids(
            MODEL_WORKLOAD,
            workload_ids,
            permission_maps=permission_maps,
            user=user,
            filters=[{"field": "workload_type", "type": "list_any[]", "value": list(BUSINESS_WORKLOAD_KINDS)}],
        )
        other_count = cls._count_ids(
            MODEL_WORKLOAD,
            workload_ids,
            permission_maps=permission_maps,
            user=user,
            filters=[{"field": "workload_type", "type": "list_none[]", "value": list(BUSINESS_WORKLOAD_KINDS)}],
        )
        return {
            "summary": {
                "namespace_count": namespace_count,
                "workload_count": business_count,
                "other_workload_count": other_count,
                "pod_count": pod_count,
                "node_count": node_count,
            },
            "collection_facts": cls._collection_facts(cluster),
            "topology": {"nodes": topology_nodes, "edges": topology_edges},
            "layers": {
                "namespace": {"shown": len(namespaces), "count": namespace_count, "page_size": 20},
                "workload": {"shown": len(workloads), "count": shown_workload_count, "page_size": 50},
                "node": {"shown": len(nodes), "count": node_count, "page_size": 50},
            },
        }

    @classmethod
    def get_workload_pods(cls, cluster_id, workload_id, page=1, page_size=50, permission_maps=None, user=None):
        return cls._get_workload_pods_batched(
            cluster_id, workload_id, page=page, page_size=page_size,
            permission_maps=permission_maps, user=user,
        )

    @classmethod
    def _get_workload_pods_batched(
        cls, cluster_id, workload_id, page=1, page_size=50, permission_maps=None, user=None
    ):
        cluster = InstanceManage.query_entity_by_id(int(cluster_id))
        if not cluster or cluster.get("model_id") != MODEL_CLUSTER:
            raise ValidationError("实例不存在或不是 k8s_cluster")

        namespace_ids = cls._relation_ids(
            InstanceManage.instance_association_map(MODEL_CLUSTER, [int(cluster_id)], MODEL_NAMESPACE)
        )
        namespace_ids = cls._visible_candidate_ids(
            MODEL_NAMESPACE, namespace_ids, permission_maps=permission_maps, user=user
        )
        workload_map = InstanceManage.instance_association_map(MODEL_NAMESPACE, namespace_ids, MODEL_WORKLOAD)
        cluster_workload_ids = set(cls._relation_ids(workload_map))
        normalized_workload_id = int(workload_id)
        if normalized_workload_id not in cluster_workload_ids:
            raise ValidationError("Workload 不属于当前集群或无权限")
        workload_permission = (permission_maps or {}).get(MODEL_WORKLOAD)
        if workload_permission and cls._count_ids(
            MODEL_WORKLOAD,
            [normalized_workload_id],
            permission_maps=permission_maps,
            user=user,
        ) != 1:
            raise ValidationError("Workload 不属于当前集群或无权限")

        pod_ids = cls._relation_ids(
            InstanceManage.instance_association_map(MODEL_WORKLOAD, [normalized_workload_id], MODEL_POD)
        )
        pods, count = cls._query_page(
            MODEL_POD, pod_ids, page=int(page), page_size=int(page_size), order="name",
            permission_maps=permission_maps, user=user,
        )
        current_pod_ids = [_id(pod) for pod in pods if _id(pod) is not None]
        pod_node_map = InstanceManage.instance_association_map(MODEL_POD, current_pod_ids, MODEL_NODE)
        node_ids = cls._relation_ids(pod_node_map)
        node_rows, _ = cls._query_page(
            MODEL_NODE, node_ids, page_size=max(1, len(node_ids)), order="name",
            permission_maps=permission_maps, user=user,
        )
        nodes_by_id = {_id(node): node for node in node_rows}

        result_nodes = []
        result_edges = []
        seen_nodes = set()
        for pod in pods:
            pod_id = _id(pod)
            result_nodes.append(cls._node(pod, "pod"))
            result_edges.append(cls._edge(normalized_workload_id, pod_id, "workload-pod"))
            related_node_ids = pod_node_map.get(pod_id, [])
            related_node_id = related_node_ids[0] if related_node_ids else None
            if related_node_id in nodes_by_id:
                node = cls._node(nodes_by_id[related_node_id], "node")
                target_id = related_node_id
            elif related_node_id is not None:
                node = {
                    "id": "virtual:node-forbidden",
                    "model_id": "virtual",
                    "name": "目标 Node 无权限",
                    "layer": "node",
                }
                target_id = "virtual:node-forbidden"
            elif pod.get("node"):
                node = {
                    "id": "virtual:node-unmatched",
                    "model_id": "virtual",
                    "name": "Node 未匹配",
                    "layer": "node",
                }
                target_id = "virtual:node-unmatched"
            else:
                node = {
                    "id": "virtual:unscheduled",
                    "model_id": "virtual",
                    "name": "未调度",
                    "layer": "node",
                }
                target_id = "virtual:unscheduled"
            if node["model_id"] == "virtual" and node["id"] not in seen_nodes:
                seen_nodes.add(node["id"])
                result_nodes.append(node)
            result_edges.append(cls._edge(pod_id, target_id, "pod-node"))

        return {
            "nodes": result_nodes,
            "edges": result_edges,
            "count": count,
            "page": int(page),
            "page_size": int(page_size),
        }

    @classmethod
    def get_unowned_pods(cls, cluster_id, page=1, page_size=50, permission_maps=None, user=None):
        return cls._get_unowned_pods_batched(
            cluster_id, page=page, page_size=page_size, permission_maps=permission_maps, user=user
        )

    @classmethod
    def _get_unowned_pods_batched(
        cls, cluster_id, *, page, page_size, permission_maps=None, user=None
    ):
        cluster = InstanceManage.query_entity_by_id(int(cluster_id))
        if not cluster or cluster.get("model_id") != MODEL_CLUSTER:
            raise ValidationError("实例不存在或不是 k8s_cluster")
        namespace_ids = cls._relation_ids(
            InstanceManage.instance_association_map(MODEL_CLUSTER, [int(cluster_id)], MODEL_NAMESPACE)
        )
        namespace_ids = cls._visible_candidate_ids(
            MODEL_NAMESPACE, namespace_ids, permission_maps=permission_maps, user=user
        )
        workload_map = InstanceManage.instance_association_map(MODEL_NAMESPACE, namespace_ids, MODEL_WORKLOAD)
        direct_pod_map = InstanceManage.instance_association_map(MODEL_NAMESPACE, namespace_ids, MODEL_POD)
        owned_pod_ids = set(cls._relation_ids(
            InstanceManage.instance_association_map(MODEL_WORKLOAD, cls._relation_ids(workload_map), MODEL_POD)
        ))
        direct_parent = {
            pod_id: namespace_id
            for namespace_id, pod_ids in direct_pod_map.items()
            for pod_id in pod_ids
            if pod_id not in owned_pod_ids
        }
        pods, count = cls._query_page(
            MODEL_POD, sorted(direct_parent), page=page, page_size=page_size, order="name",
            permission_maps=permission_maps, user=user,
        )
        current_ids = [_id(pod) for pod in pods]
        pod_node_map = InstanceManage.instance_association_map(MODEL_POD, current_ids, MODEL_NODE)
        node_ids = cls._relation_ids(pod_node_map)
        node_rows, _ = cls._query_page(
            MODEL_NODE, node_ids, page_size=max(1, len(node_ids)), order="name",
            permission_maps=permission_maps, user=user,
        )
        nodes_by_id = {_id(node): node for node in node_rows}
        nodes = []
        edges = []
        seen_virtual = set()
        for pod in pods:
            pod_id = _id(pod)
            nodes.append(cls._node(pod, "pod"))
            edges.append(cls._edge(direct_parent[pod_id], pod_id, "namespace-pod"))
            related_node_id = next(iter(pod_node_map.get(pod_id, [])), None)
            if related_node_id in nodes_by_id:
                target_id = related_node_id
            elif related_node_id is not None:
                target_id = "virtual:node-forbidden"
                if target_id not in seen_virtual:
                    seen_virtual.add(target_id)
                    nodes.append({"id": target_id, "model_id": "virtual", "name": "目标 Node 无权限", "layer": "node"})
            elif pod.get("node"):
                target_id = "virtual:node-unmatched"
                if target_id not in seen_virtual:
                    seen_virtual.add(target_id)
                    nodes.append({"id": target_id, "model_id": "virtual", "name": "Node 未匹配", "layer": "node"})
            else:
                target_id = "virtual:unscheduled"
                if target_id not in seen_virtual:
                    seen_virtual.add(target_id)
                    nodes.append({"id": target_id, "model_id": "virtual", "name": "未调度", "layer": "node"})
            edges.append(cls._edge(pod_id, target_id, "pod-node"))
        return {"nodes": nodes, "edges": edges, "count": count, "page": int(page), "page_size": int(page_size)}

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
        return cls._list_resources_batched(
            cluster_id,
            kind,
            page=page,
            page_size=page_size,
            search=search,
            order=order,
            namespace_id=namespace_id,
            workload_id=workload_id,
            node_id=node_id,
            permission_maps=permission_maps,
            user=user,
        )

    @classmethod
    def _list_resources_batched(
        cls,
        cluster_id,
        kind,
        *,
        page,
        page_size,
        search,
        order,
        namespace_id,
        workload_id,
        node_id,
        permission_maps,
        user,
    ):
        cluster = InstanceManage.query_entity_by_id(int(cluster_id))
        if not cluster or cluster.get("model_id") != MODEL_CLUSTER:
            raise ValidationError("实例不存在或不是 k8s_cluster")

        namespace_ids = cls._relation_ids(
            InstanceManage.instance_association_map(MODEL_CLUSTER, [int(cluster_id)], MODEL_NAMESPACE)
        )
        namespace_ids = cls._visible_candidate_ids(
            MODEL_NAMESPACE, namespace_ids, permission_maps=permission_maps, user=user
        )
        node_ids = cls._relation_ids(
            InstanceManage.instance_association_map(MODEL_CLUSTER, [int(cluster_id)], MODEL_NODE)
        )
        normalized_namespace_id = int(namespace_id) if namespace_id is not None else None
        normalized_workload_id = int(workload_id) if workload_id is not None else None
        normalized_node_id = int(node_id) if node_id is not None else None
        if normalized_namespace_id is not None and normalized_namespace_id not in namespace_ids:
            raise ValidationError("Namespace 不属于当前集群或无权限")
        if normalized_node_id is not None and normalized_node_id not in node_ids:
            raise ValidationError("Node 不属于当前集群或无权限")

        filters = []
        if search:
            filters.append({"field": "name", "type": "str*", "value": str(search)})

        if kind == "namespace":
            rows, count = cls._query_page(
                MODEL_NAMESPACE, namespace_ids, page=page, page_size=page_size, order=order, filters=filters,
                permission_maps=permission_maps, user=user,
            )
            current_ids = [_id(row) for row in rows]
            workload_map = InstanceManage.instance_association_map(MODEL_NAMESPACE, current_ids, MODEL_WORKLOAD)
            direct_pod_map = InstanceManage.instance_association_map(MODEL_NAMESPACE, current_ids, MODEL_POD)
            workload_pod_map = InstanceManage.instance_association_map(
                MODEL_WORKLOAD, cls._relation_ids(workload_map), MODEL_POD
            )
            items = []
            for row in rows:
                item_id = _id(row)
                workload_ids = workload_map.get(item_id, [])
                pod_ids = set(direct_pod_map.get(item_id, []))
                for related_workload_id in workload_ids:
                    pod_ids.update(workload_pod_map.get(related_workload_id, []))
                items.append({
                    "id": str(item_id),
                    "name": _name(row),
                    "workload_count": len(workload_ids),
                    "pod_count": len(pod_ids),
                })
        elif kind == "node":
            rows, count = cls._query_page(
                MODEL_NODE, node_ids, page=page, page_size=page_size, order=order, filters=filters,
                permission_maps=permission_maps, user=user,
            )
            items = [
                {
                    "id": str(_id(row)),
                    "name": _name(row),
                    "role": row.get("role"),
                    "cpu": row.get("cpu"),
                    "memory": row.get("memory"),
                    "disk": row.get("disk"),
                }
                for row in rows
            ]
        elif kind in BUSINESS_WORKLOAD_KINDS or kind == "other_workload":
            scoped_namespace_ids = [normalized_namespace_id] if normalized_namespace_id is not None else namespace_ids
            workload_map = InstanceManage.instance_association_map(
                MODEL_NAMESPACE, scoped_namespace_ids, MODEL_WORKLOAD
            )
            candidate_ids = cls._relation_ids(workload_map)
            workload_namespace = {
                related_id: parent_id
                for parent_id, related_ids in workload_map.items()
                for related_id in related_ids
            }
            if normalized_workload_id is not None and normalized_workload_id not in candidate_ids:
                raise ValidationError("Workload 不属于当前集群或无权限")
            type_filter = {
                "field": "workload_type",
                "type": "list_none[]" if kind == "other_workload" else "list_any[]",
                "value": list(BUSINESS_WORKLOAD_KINDS) if kind == "other_workload" else [kind],
            }
            rows, count = cls._query_page(
                MODEL_WORKLOAD, candidate_ids, page=page, page_size=page_size, order=order,
                filters=[*filters, type_filter], permission_maps=permission_maps, user=user,
            )
            current_ids = [_id(row) for row in rows]
            pod_map = InstanceManage.instance_association_map(MODEL_WORKLOAD, current_ids, MODEL_POD)
            parent_ids = sorted({workload_namespace[item_id] for item_id in current_ids})
            parent_rows, _ = cls._query_page(
                MODEL_NAMESPACE, parent_ids, page_size=max(1, len(parent_ids)), order="name",
                permission_maps=permission_maps, user=user,
            )
            parent_by_id = {_id(row): row for row in parent_rows}
            items = []
            for row in rows:
                item_id = _id(row)
                parent_id = workload_namespace[item_id]
                items.append({
                    "id": str(item_id),
                    "name": _name(row),
                    "namespace": _name(parent_by_id[parent_id]) if parent_id in parent_by_id else None,
                    "namespace_id": str(parent_id),
                    "workload_type": _workload_type(row),
                    "replicas": row.get("replicas"),
                    "pod_count": len(pod_map.get(item_id, [])),
                })
        else:
            workload_map = InstanceManage.instance_association_map(MODEL_NAMESPACE, namespace_ids, MODEL_WORKLOAD)
            all_workload_ids = cls._relation_ids(workload_map)
            if normalized_workload_id is not None and normalized_workload_id not in all_workload_ids:
                raise ValidationError("Workload 不属于当前集群或无权限")
            if normalized_workload_id is not None:
                candidate_ids = cls._relation_ids(
                    InstanceManage.instance_association_map(MODEL_WORKLOAD, [normalized_workload_id], MODEL_POD)
                )
            elif normalized_node_id is not None:
                candidate_ids = cls._relation_ids(
                    InstanceManage.instance_association_map(MODEL_NODE, [normalized_node_id], MODEL_POD)
                )
            else:
                scoped_namespace_ids = [normalized_namespace_id] if normalized_namespace_id is not None else namespace_ids
                scoped_workload_map = {
                    parent_id: related_ids
                    for parent_id, related_ids in workload_map.items()
                    if parent_id in scoped_namespace_ids
                }
                direct_ids = cls._relation_ids(
                    InstanceManage.instance_association_map(MODEL_NAMESPACE, scoped_namespace_ids, MODEL_POD)
                )
                owned_ids = cls._relation_ids(
                    InstanceManage.instance_association_map(
                        MODEL_WORKLOAD, cls._relation_ids(scoped_workload_map), MODEL_POD
                    )
                )
                candidate_ids = sorted(set(direct_ids) | set(owned_ids))
            rows, count = cls._query_page(
                MODEL_POD, candidate_ids, page=page, page_size=page_size, order=order, filters=filters,
                permission_maps=permission_maps, user=user,
            )
            current_ids = [_id(row) for row in rows]
            pod_namespace_map = InstanceManage.instance_association_map(MODEL_POD, current_ids, MODEL_NAMESPACE)
            pod_workload_map = InstanceManage.instance_association_map(MODEL_POD, current_ids, MODEL_WORKLOAD)
            parent_ids = cls._relation_ids(pod_namespace_map)
            owner_ids = cls._relation_ids(pod_workload_map)
            parent_rows, _ = cls._query_page(
                MODEL_NAMESPACE, parent_ids, page_size=max(1, len(parent_ids)), order="name",
                permission_maps=permission_maps, user=user,
            )
            owner_rows, _ = cls._query_page(
                MODEL_WORKLOAD, owner_ids, page_size=max(1, len(owner_ids)), order="name",
                permission_maps=permission_maps, user=user,
            )
            parent_by_id = {_id(row): row for row in parent_rows}
            owner_by_id = {_id(row): row for row in owner_rows}
            items = []
            for row in rows:
                item_id = _id(row)
                parent_id = next(iter(pod_namespace_map.get(item_id, [])), None)
                owner_id = next(iter(pod_workload_map.get(item_id, [])), None)
                items.append({
                    "id": str(item_id),
                    "name": _name(row),
                    "namespace": _name(parent_by_id[parent_id]) if parent_id in parent_by_id else None,
                    "namespace_id": str(parent_id) if parent_id is not None else None,
                    "workload": _name(owner_by_id[owner_id]) if owner_id in owner_by_id else None,
                    "workload_id": str(owner_id) if owner_id is not None else None,
                    "node": row.get("node"),
                    "ip_addr": row.get("ip_addr"),
                    "request_cpu": row.get("request_cpu"),
                    "request_memory": row.get("request_memory"),
                    "limit_cpu": row.get("limit_cpu"),
                    "limit_memory": row.get("limit_memory"),
                })

        return {"items": items, "count": count, "page": int(page), "page_size": int(page_size)}

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
        return cls._get_layer_batched(
            cluster_id,
            layer,
            page=page,
            page_size=page_size,
            namespace_ids=namespace_ids,
            permission_maps=permission_maps,
            user=user,
        )

    @classmethod
    def _get_layer_batched(
        cls, cluster_id, layer, *, page, page_size, namespace_ids, permission_maps=None, user=None
    ):
        cluster = InstanceManage.query_entity_by_id(int(cluster_id))
        if not cluster or cluster.get("model_id") != MODEL_CLUSTER:
            raise ValidationError("实例不存在或不是 k8s_cluster")
        normalized_page_size = int(page_size or LAYER_LIMITS[layer])
        if normalized_page_size > LAYER_LIMITS[layer]:
            raise ValidationError(f"{layer} page_size 不能超过 {LAYER_LIMITS[layer]}")

        if layer in {"namespace", "node"}:
            model_id = MODEL_NAMESPACE if layer == "namespace" else MODEL_NODE
            candidate_ids = cls._relation_ids(
                InstanceManage.instance_association_map(MODEL_CLUSTER, [int(cluster_id)], model_id)
            )
            rows, count = cls._query_page(
                model_id, candidate_ids, page=page, page_size=normalized_page_size, order="name",
                permission_maps=permission_maps, user=user,
            )
            parent_id = _id(cluster)
            edge_kind = f"cluster-{layer}"
            edges = [cls._edge(parent_id, _id(row), edge_kind) for row in rows]
        else:
            cluster_namespace_ids = cls._visible_candidate_ids(
                MODEL_NAMESPACE,
                cls._relation_ids(
                InstanceManage.instance_association_map(MODEL_CLUSTER, [int(cluster_id)], MODEL_NAMESPACE)
                ),
                permission_maps=permission_maps,
                user=user,
            )
            cluster_namespace_ids = set(cluster_namespace_ids)
            normalized_namespace_ids = {int(item) for item in (namespace_ids or [])}
            if not normalized_namespace_ids or not normalized_namespace_ids.issubset(cluster_namespace_ids):
                raise ValidationError("Workload 分层查询必须提供当前集群内已加载的 Namespace")
            workload_map = InstanceManage.instance_association_map(
                MODEL_NAMESPACE, sorted(normalized_namespace_ids), MODEL_WORKLOAD
            )
            workload_parent = {
                workload_id: namespace_id
                for namespace_id, workload_ids in workload_map.items()
                for workload_id in workload_ids
            }
            rows, count = cls._query_page(
                MODEL_WORKLOAD, sorted(workload_parent), page=page, page_size=normalized_page_size, order="name",
                permission_maps=permission_maps, user=user,
            )
            edges = [
                cls._edge(workload_parent[_id(row)], _id(row), "namespace-workload") for row in rows
            ]
        return {
            "nodes": [cls._node(row, layer) for row in rows],
            "edges": edges,
            "count": count,
            "page": int(page),
            "page_size": normalized_page_size,
        }
