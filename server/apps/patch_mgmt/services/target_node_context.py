"""补丁目标对应的节点管理上下文。"""

from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.models import Node
from apps.patch_mgmt.constants import PatchTargetSource
from apps.patch_mgmt.models import PatchTarget


def is_container_target(target: PatchTarget) -> bool:
    """仅节点管理纳入且当前 Node 明确为 container 时返回 True。"""
    if target.source_type != PatchTargetSource.NODE_MGMT or not target.node_id:
        return False
    return Node.objects.filter(
        pk=target.node_id,
        node_type=ControllerConstants.NODE_TYPE_CONTAINER,
    ).exists()


def container_target_ids(target_ids: list[int]) -> list[int]:
    """批量返回对应容器节点的补丁目标 ID，避免逐主机查询。"""
    targets = list(
        PatchTarget.objects.filter(
            pk__in=target_ids,
            source_type=PatchTargetSource.NODE_MGMT,
        )
        .exclude(node_id="")
        .only("id", "node_id")
    )
    container_node_ids = set(
        Node.objects.filter(
            pk__in=[target.node_id for target in targets],
            node_type=ControllerConstants.NODE_TYPE_CONTAINER,
        ).values_list("id", flat=True)
    )
    return sorted(target.id for target in targets if target.node_id in container_node_ids)
