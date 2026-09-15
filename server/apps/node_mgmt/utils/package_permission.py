"""包写权限判定。

导入探针包与「恢复内置」在节点和监控两个模块都有入口，两边必须落到同一套判定，
否则只拿到监控侧权限的人可以撤销节点侧的导入。
"""

from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.node_mgmt.constants.package import PackageConstants

PACKAGE_WRITE_PERMISSIONS = {
    (PackageConstants.TYPE_CONTROLLER, "create"): {
        "controller_list-AddPacket",
        "controller_packet-AddPacket",
    },
    (PackageConstants.TYPE_CONTROLLER, "destroy"): {"controller_packet-Delete"},
    (PackageConstants.TYPE_COLLECTOR, "create"): {
        "collector_list-AddPacket",
        "collector_packet-AddPacket",
    },
    (PackageConstants.TYPE_COLLECTOR, "destroy"): {"collector_packet-Delete"},
}
NODE_APP_ADMIN_ROLE = "node--admin"


def require_package_write_permission(request, package_type, action):
    required_permissions = PACKAGE_WRITE_PERMISSIONS.get((package_type, action))
    if not required_permissions:
        raise ValidationError({"type": ["不支持的包类型"]})

    user_roles = getattr(request.user, "roles", ()) or ()
    if getattr(request.user, "is_superuser", False) or NODE_APP_ADMIN_ROLE in user_roles:
        return

    user_permissions = getattr(request.user, "permission", set()) or set()
    if isinstance(user_permissions, dict):
        user_permissions = user_permissions.get("node", set())

    if required_permissions.isdisjoint(user_permissions):
        raise PermissionDenied()


def require_collector_pack_write(request):
    """导入 / 恢复探针包统一使用的权限判定。"""
    require_package_write_permission(request, PackageConstants.TYPE_COLLECTOR, "create")
