"""节点管理统一 OpenAPI 网关端点。"""

from django.core.exceptions import ObjectDoesNotExist

from apps.core.openapi.decorators import openapi_expose
from apps.core.openapi.envelope import ErrorCode
from apps.node_mgmt.openapi_serializers import (
    EnvironmentInstallRequestSerializer,
    EnvironmentStatusRequestSerializer,
    NodeCloudRegionQuerySerializer,
    NodeCollectorInstallSerializer,
    NodeCollectorOperateSerializer,
    NodeConfigurationBindSerializer,
    NodeControllerInstallSerializer,
    NodeDetailQuerySerializer,
    NodeInstallCommandSerializer,
    NodeInstallTaskQuerySerializer,
    NodeListQuerySerializer,
    NodePackageQuerySerializer,
)
from apps.node_mgmt.openapi_service import (
    bind_configuration,
    controller_install_command,
    get_node,
    install_collector,
    install_controller,
    install_task,
    list_cloud_regions,
    list_nodes,
    list_packages,
    operate_collector,
)
from apps.node_mgmt.services.environment_install import EnvironmentInstallService

_ORG_SCOPE = "组织口径：API 令牌绑定组织精确匹配，不级联子组织"
_CATALOG_SCOPE = "云区域是平台目录，不按组织拆分；调用仍须绑定组织"
_STATUS_SCOPE = "在线状态与节点列表一致，按 60 秒内心跳判断；采集器状态与列表展示口径一致"


@openapi_expose(
    path="node/cloud-regions",
    method="GET",
    schema=NodeCloudRegionQuerySerializer,
    inject="team_list_with_user",
    permission="cloud_region_list-View",
    permission_app="node",
    summary=f"分页查询云区域（{_CATALOG_SCOPE}）",
)
def openapi_list_cloud_regions(page=1, page_size=20, keyword="", *, team=None, user_info=None):
    del user_info
    return list_cloud_regions(team=team, page=page, page_size=page_size, keyword=keyword)


@openapi_expose(
    path="node/nodes",
    method="GET",
    schema=NodeListQuerySerializer,
    inject="team_list_with_user",
    permission="cloud_region_node-View",
    permission_app="node",
    summary=f"分页查询节点及采集器、控制器状态（{_ORG_SCOPE}；{_STATUS_SCOPE}）",
)
def openapi_list_nodes(
    page=1,
    page_size=20,
    keyword="",
    cloud_region_id=None,
    *,
    team=None,
    user_info=None,
):
    del user_info
    return list_nodes(
        team=team,
        page=page,
        page_size=page_size,
        keyword=keyword,
        cloud_region_id=cloud_region_id,
    )


@openapi_expose(
    path="node/nodes/detail",
    method="GET",
    schema=NodeDetailQuerySerializer,
    inject="team_list_with_user",
    permission="cloud_region_node-View",
    permission_app="node",
    summary=f"查询单个节点（跨组织按不存在处理，{_ORG_SCOPE}；{_STATUS_SCOPE}）",
)
def openapi_get_node(node_id, *, team=None, user_info=None):
    del user_info
    return get_node(team=team, node_id=node_id)


@openapi_expose(
    path="node/packages",
    method="GET",
    schema=NodePackageQuerySerializer,
    inject="team_list_with_user",
    permission="cloud_region_node-Edit",
    permission_app="node",
    summary=f"分页查询可安装的控制器或采集器安装包，不能上传或删除（{_ORG_SCOPE}）",
)
def openapi_list_packages(page=1, page_size=20, keyword="", package_type=None, os="", *, team=None, user_info=None):
    del user_info
    return list_packages(team=team, page=page, page_size=page_size, keyword=keyword, package_type=package_type, os=os)


@openapi_expose(
    path="node/controllers/install",
    method="POST",
    schema=NodeControllerInstallSerializer,
    inject="team_list_with_user",
    permission="cloud_region_node-Edit",
    permission_app="node",
    summary=f"远程安装控制器并返回任务号；目标组织强制为令牌绑定组织（{_ORG_SCOPE}）",
)
def openapi_install_controller(cloud_region_id, work_node, package_id, cpu_architecture, nodes, *, team=None, user_info=None):
    return install_controller(
        team=team,
        user_info=user_info,
        cloud_region_id=cloud_region_id,
        work_node=work_node,
        package_id=package_id,
        cpu_architecture=cpu_architecture,
        nodes=nodes,
    )


@openapi_expose(
    path="node/controllers/install-command",
    method="POST",
    schema=NodeInstallCommandSerializer,
    inject="team_list_with_user",
    permission="cloud_region_node-Edit",
    permission_app="node",
    summary=f"生成在目标主机上手动安装控制器的命令（{_ORG_SCOPE}）",
)
def openapi_controller_install_command(
    ip,
    node_id,
    os,
    cpu_architecture,
    package_id,
    cloud_region_id,
    node_name="",
    *,
    team=None,
    user_info=None,
):
    return controller_install_command(
        team=team,
        user_info=user_info,
        ip=ip,
        node_id=node_id,
        os=os,
        cpu_architecture=cpu_architecture,
        package_id=package_id,
        cloud_region_id=cloud_region_id,
        node_name=node_name,
    )


@openapi_expose(
    path="node/install-tasks",
    method="GET",
    schema=NodeInstallTaskQuerySerializer,
    inject="team_list_with_user",
    permission="cloud_region_node-Edit",
    permission_app="node",
    summary=f"查询控制器或采集器安装进度，只返回本组织节点（{_ORG_SCOPE}）",
)
def openapi_install_task(task_type, task_id, *, team=None, user_info=None):
    del user_info
    return install_task(team=team, task_type=task_type, task_id=task_id)


@openapi_expose(
    path="node/collectors/install",
    method="POST",
    schema=NodeCollectorInstallSerializer,
    inject="team_list_with_user",
    permission="cloud_region_node-OperateCollector",
    permission_app="node",
    summary=f"在已有节点上安装采集器并返回任务号（{_ORG_SCOPE}）",
)
def openapi_install_collector(package_id, node_ids, *, team=None, user_info=None):
    del user_info
    return install_collector(team=team, package_id=package_id, node_ids=node_ids)


@openapi_expose(
    path="node/collectors/operate",
    method="POST",
    schema=NodeCollectorOperateSerializer,
    inject="team_list_with_user",
    permission="cloud_region_node-OperateCollector",
    permission_app="node",
    summary=f"启停本组织节点上的采集器（{_ORG_SCOPE}）",
)
def openapi_operate_collector(node_ids, collector_id, operation, *, team=None, user_info=None):
    return operate_collector(
        team=team,
        user_info=user_info,
        node_ids=node_ids,
        collector_id=collector_id,
        operation=operation,
    )


@openapi_expose(
    path="node/configurations/bind",
    method="POST",
    schema=NodeConfigurationBindSerializer,
    inject="team_list_with_user",
    permission="cloud_region_node-EditMainConfiguration",
    permission_app="node",
    summary=f"把采集配置绑定到本组织节点并下发（{_ORG_SCOPE}）",
)
def openapi_bind_configuration(node_ids, collector_configuration_id, *, team=None, user_info=None):
    del user_info
    return bind_configuration(team=team, node_ids=node_ids, collector_configuration_id=collector_configuration_id)


def _invoke_install_service(operation, **kwargs):
    try:
        return operation(**kwargs)
    except (PermissionError, ObjectDoesNotExist):
        return {"result": False, "code": ErrorCode.TEAM_OUT_OF_SCOPE, "message": "installation grant denied"}
    except ValueError as error:
        return {"result": False, "message": str(error)}


@openapi_expose(
    path="node-mgmt/environment-install-status",
    method="POST",
    schema=EnvironmentStatusRequestSerializer,
    inject="team_list_with_user",
    summary="查询环境授权范围内的安装结果",
)
def environment_install_status(grant_id, installation_key, install_id, report=None, *, team=None, user_info=None):
    # Explicit capability authorization in service; grant export requires node Edit permission.
    return _invoke_install_service(
        EnvironmentInstallService.status,
        grant_id=grant_id,
        installation_key=installation_key,
        install_id=install_id,
        team=team,
        user_info=user_info,
        report=report,
    )


@openapi_expose(
    path="node-mgmt/environment-install",
    method="POST",
    schema=EnvironmentInstallRequestSerializer,
    inject="team_list_with_user",
    summary="使用环境安装授权申请独立节点会话",
)
def environment_install(grant_id, installation_key, request_id, node_id, ip, node_name, os, cpu_architecture, *, team=None, user_info=None):
    return _invoke_install_service(
        EnvironmentInstallService.request,
        grant_id=grant_id,
        installation_key=installation_key,
        request_id=request_id,
        node_id=node_id,
        ip=ip,
        node_name=node_name,
        os=os,
        cpu_architecture=cpu_architecture,
        team=team,
        user_info=user_info,
    )
