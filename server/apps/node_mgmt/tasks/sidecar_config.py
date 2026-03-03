from celery import shared_task

from apps.core.logger import logger
from apps.node_mgmt.models import Node
from apps.node_mgmt.services.sidecar_config import SidecarConfigService


@shared_task
def sync_node_properties_to_sidecar(
    node_id: str, name: str | None = None, organizations: list[str] | None = None
):
    """
    异步同步节点属性到远程 sidecar.yaml 配置文件

    Args:
        node_id: 节点 ID
        name: 新的节点名称（可选）
        organizations: 新的组织 ID 列表（可选）
    """
    try:
        node = Node.objects.get(id=node_id)
    except Node.DoesNotExist:
        logger.warning(f"Node not found for sidecar config sync: {node_id}")
        return {"success": False, "error": "Node not found"}

    try:
        SidecarConfigService.sync_node_properties(
            node, name=name, organizations=organizations
        )
        return {"success": True}
    except ValueError as e:
        logger.warning(
            f"Failed to sync node properties to sidecar for node {node_id}: {e}"
        )
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.exception(
            f"Unexpected error syncing node properties to sidecar for node {node_id}"
        )
        return {"success": False, "error": str(e)}
