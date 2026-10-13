"""节点只读目录查询。在线状态与节点列表一致：60 秒内心跳。"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.node_mgmt.models import (
    CloudRegion,
    Collector,
    Node,
    NodeCollectorInstallStatus,
    NodeComponentVersion,
)
from apps.node_mgmt.services.node_status_filter import ACTIVE_WINDOW_SECONDS, hosted_collectors_for_filter


def team_ids(team):
    ids = []
    for item in team or []:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value > 0:
            ids.append(value)
    return ids


def list_cloud_regions(*, team, page, page_size, keyword):
    if not team_ids(team):
        return _empty_page(page, page_size)
    queryset = CloudRegion.objects.all().order_by("id")
    if keyword:
        queryset = queryset.filter(name__icontains=keyword)
    total = queryset.count()
    start = (page - 1) * page_size
    items = [_region_item(row) for row in queryset[start : start + page_size]]
    return {"count": total, "page": page, "page_size": page_size, "items": items}


def list_nodes(*, team, page, page_size, keyword, cloud_region_id=None):
    queryset = _node_queryset(team, keyword, cloud_region_id)
    total = queryset.count()
    start = (page - 1) * page_size
    rows = list(queryset[start : start + page_size])
    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "items": _project_nodes(rows),
    }


def get_node(*, team, node_id):
    node = _node_queryset(team, "", None).filter(id=node_id).first()
    if node is None:
        return {"result": False, "message": "节点不存在"}
    return _project_nodes([node])[0]


def _node_queryset(team, keyword, cloud_region_id):
    ids = team_ids(team)
    if not ids:
        return Node.objects.none()
    queryset = Node.objects.filter(nodeorganization__organization__in=ids).distinct().order_by("name", "id")
    if cloud_region_id:
        queryset = queryset.filter(cloud_region_id=cloud_region_id)
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(ip__icontains=keyword))
    return queryset


def _project_nodes(nodes):
    node_ids = [node.id for node in nodes]
    collector_name_by_id = dict(Collector.objects.values_list("id", "name"))
    install_by_node = {}
    for row in NodeCollectorInstallStatus.objects.filter(node_id__in=node_ids).values("node_id", "collector_id", "status"):
        install_by_node.setdefault(row["node_id"], []).append(row)
    controllers_by_node = {}
    for version in NodeComponentVersion.objects.filter(node_id__in=node_ids, component_type="controller").order_by("component_id"):
        controllers_by_node.setdefault(version.node_id, []).append(
            {
                "component_id": version.component_id,
                "version": version.version,
                "upgradeable": version.upgradeable,
            }
        )
    cutoff = timezone.now() - timedelta(seconds=ACTIVE_WINDOW_SECONDS)
    items = []
    for node in nodes:
        reported = node.status.get("collectors") if isinstance(node.status, dict) else None
        collectors = hosted_collectors_for_filter(reported, install_by_node.get(node.id, []), collector_name_by_id)
        items.append(
            {
                "id": node.id,
                "name": node.name,
                "ip": node.ip,
                "operating_system": node.operating_system,
                "cpu_architecture": node.cpu_architecture,
                "cloud_region_id": node.cloud_region_id,
                "node_type": node.node_type,
                "install_method": node.install_method,
                "online": bool(node.updated_at and node.updated_at > cutoff),
                "collectors": [
                    {
                        "collector_id": item["collector_id"],
                        "collector_name": item["collector_name"],
                        "status": item["status"],
                    }
                    for item in collectors
                ],
                "controllers": controllers_by_node.get(node.id, []),
            }
        )
    return items


def _region_item(region):
    return {"id": region.id, "name": region.name, "introduction": region.introduction}


def _empty_page(page, page_size):
    return {"count": 0, "page": page, "page_size": page_size, "items": []}


def _rejected(message):
    return {"result": False, "message": message}


def _public_message(exc, fallback):
    text = str(exc)
    lowered = text.lower()
    if "http" in lowered or "token" in lowered or "password" in lowered or "private_key" in lowered or len(text) > 200:
        return fallback
    return text or fallback


def _run(action, fallback):
    from apps.core.exceptions.base_app_exception import BaseAppException

    try:
        return action()
    except BaseAppException as exc:
        return _rejected(_public_message(exc, fallback))
    except Exception:
        return _rejected(fallback)


def _actor(team, user_info):
    ids = team_ids(team)
    if not ids:
        return None
    info = user_info or {}
    return {"username": info.get("user") or "", "domain": info.get("domain") or "domain.com", "organization_ids": ids}


def _owned_node_ids(ids, node_ids):
    from apps.node_mgmt.models import NodeOrganization

    requested = [str(node_id) for node_id in node_ids if node_id]
    owned = set(NodeOrganization.objects.filter(organization__in=ids, node_id__in=requested).values_list("node_id", flat=True))
    return requested, owned


def list_packages(*, team, page, page_size, keyword, package_type=None, os=""):
    from apps.node_mgmt.services.package import PackageService

    if not team_ids(team):
        return _empty_page(page, page_size)
    queryset = PackageService.ready_queryset().order_by("-id")
    if package_type:
        queryset = queryset.filter(type=package_type)
    if os:
        queryset = queryset.filter(os=os)
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(object__icontains=keyword) | Q(version__icontains=keyword))
    total = queryset.count()
    start = (page - 1) * page_size
    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "items": [_package_item(row) for row in queryset[start : start + page_size]],
    }


def install_controller(*, team, user_info, cloud_region_id, work_node, package_id, cpu_architecture, nodes):
    from rest_framework.exceptions import ValidationError

    from apps.node_mgmt.serializers.installer import ControllerInstallRequestSerializer
    from apps.node_mgmt.services.installer import InstallerService
    from apps.node_mgmt.tasks.installer import install_controller as install_controller_task

    actor = _actor(team, user_info)
    if actor is None:
        return _rejected("节点不存在")
    prepared = []
    existing_ids = []
    for node in nodes:
        item = dict(node)
        item.pop("organizations", None)
        item["organizations"] = actor["organization_ids"]
        if item.get("node_id"):
            existing_ids.append(item["node_id"])
        prepared.append(item)
    requested, owned = _owned_node_ids(actor["organization_ids"], existing_ids)
    if set(requested) - owned:
        return _rejected("节点不存在")
    serializer = ControllerInstallRequestSerializer(
        data={
            "cloud_region_id": cloud_region_id,
            "work_node": work_node,
            "package_id": package_id,
            "cpu_architecture": cpu_architecture,
            "nodes": prepared,
        }
    )
    try:
        serializer.is_valid(raise_exception=True)
    except ValidationError:
        return _rejected("安装参数不合法")
    data = serializer.validated_data

    def action():
        task_id = InstallerService.install_controller(
            data["cloud_region_id"],
            data["work_node"],
            data["package_id"],
            data["nodes"],
            data["cpu_architecture"],
            actor["username"],
            actor["domain"],
        )
        install_controller_task.delay(task_id)
        return {"task_id": task_id}

    return _run(action, "控制器安装失败")


def controller_install_command(*, team, user_info, ip, node_id, os, cpu_architecture, package_id, cloud_region_id, node_name=""):
    from apps.node_mgmt.models import Node
    from apps.node_mgmt.services.installer import InstallerService

    actor = _actor(team, user_info)
    if actor is None:
        return _rejected("节点不存在")
    if Node.objects.filter(id=node_id).exists():
        requested, owned = _owned_node_ids(actor["organization_ids"], [node_id])
        if set(requested) - owned:
            return _rejected("节点不存在")

    def action():
        command = InstallerService.get_install_command(
            actor["username"],
            ip,
            node_id,
            os,
            package_id,
            cloud_region_id,
            actor["organization_ids"],
            node_name,
        )
        return {"command": command}

    return _run(action, "安装命令生成失败")


def install_task(*, team, task_type, task_id):
    from apps.node_mgmt.models.installer import CollectorTaskNode, ControllerTaskNode

    ids = team_ids(team)
    if not ids:
        return _rejected("任务不存在")
    if task_type == "controller":
        rows = list(ControllerTaskNode.objects.filter(task_id=task_id))
        visible = []
        for row in rows:
            organizations = set(row.organizations or [])
            if row.node_id:
                requested, owned = _owned_node_ids(ids, [row.node_id])
                if set(requested) - owned and not organizations.intersection(ids):
                    continue
                if not owned and not organizations.intersection(ids):
                    continue
            elif not organizations.intersection(ids):
                continue
            visible.append(
                {
                    "node_id": row.node_id,
                    "node_name": row.node_name,
                    "ip": row.ip,
                    "os": row.os,
                    "status": row.status,
                }
            )
        if not visible:
            return _rejected("任务不存在")
        return {"task_id": task_id, "task_type": task_type, "items": visible}
    rows = list(CollectorTaskNode.objects.filter(task_id=task_id))
    requested, owned = _owned_node_ids(ids, [row.node_id for row in rows])
    visible = [{"node_id": row.node_id, "status": row.status} for row in rows if row.node_id in owned]
    if not visible:
        return _rejected("任务不存在")
    return {"task_id": task_id, "task_type": task_type, "items": visible}


def install_collector(*, team, package_id, node_ids):
    from apps.node_mgmt.services.installer import InstallerService
    from apps.node_mgmt.tasks.installer import install_collector as install_collector_task

    ids = team_ids(team)
    requested, owned = _owned_node_ids(ids, node_ids)
    if not requested or set(requested) - owned:
        return _rejected("节点不存在")

    def action():
        task_id = InstallerService.install_collector(package_id, requested)
        install_collector_task.delay(task_id)
        return {"task_id": task_id}

    return _run(action, "采集器安装失败")


def operate_collector(*, team, user_info, node_ids, collector_id, operation):
    from apps.node_mgmt.services.node import NodeService

    actor = _actor(team, user_info)
    if actor is None:
        return _rejected("节点不存在")
    requested, owned = _owned_node_ids(actor["organization_ids"], node_ids)
    if not requested or set(requested) - owned:
        return _rejected("节点不存在")

    def action():
        task_id = NodeService.batch_operate_node_collector(
            requested,
            collector_id,
            operation,
            created_by=actor["username"],
            domain=actor["domain"],
            updated_by_domain=actor["domain"],
        )
        return {"task_id": task_id}

    return _run(action, "采集器操作失败")


def bind_configuration(*, team, node_ids, collector_configuration_id):
    from apps.node_mgmt.services.node import NodeService

    ids = team_ids(team)
    requested, owned = _owned_node_ids(ids, node_ids)
    if not requested or set(requested) - owned:
        return _rejected("节点不存在")

    def action():
        ok, message = NodeService.batch_binding_node_configuration(requested, collector_configuration_id)
        if not ok:
            return _rejected(message or "采集配置不存在")
        return {"node_ids": requested, "collector_configuration_id": collector_configuration_id}

    return _run(action, "采集配置绑定失败")


def _package_item(package):
    return {
        "id": package.id,
        "type": package.type,
        "os": package.os,
        "cpu_architecture": package.cpu_architecture,
        "object": package.object,
        "version": package.version,
        "name": package.name,
        "description": package.description or "",
    }
