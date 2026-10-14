"""日志统一 OpenAPI 网关端点。"""

from apps.core.openapi.decorators import openapi_expose
from apps.log.openapi_serializers import (
    LogCollectConfigUpdateSerializer,
    LogCollectInstanceCreateSerializer,
    LogCollectInstanceDeleteSerializer,
    LogCollectTypeQuerySerializer,
    LogGroupQuerySerializer,
    LogK8sCollectorCreateSerializer,
    LogK8sInstallCommandSerializer,
    LogK8sSettingSerializer,
    LogK8sStatusQuerySerializer,
    LogSearchQuerySerializer,
)
from apps.log.openapi_service import (
    create_collect_instances,
    create_k8s_collector,
    delete_collect_instances,
    k8s_install_command,
    k8s_status,
    list_collect_types,
    list_groups,
    save_k8s_setting,
    search_logs,
    update_collect_config,
)

_ORG_SCOPE = "组织口径：API 令牌绑定组织精确匹配，不级联子组织"


@openapi_expose(
    path="log/groups",
    method="GET",
    schema=LogGroupQuerySerializer,
    inject="team_list_with_user",
    permission="grouping-View",
    permission_app="log",
    summary=f"分页查询日志分组（{_ORG_SCOPE}）",
)
def openapi_list_groups(page=1, page_size=20, keyword="", *, team=None, user_info=None):
    del user_info
    return list_groups(team=team, page=page, page_size=page_size, keyword=keyword)


@openapi_expose(
    path="log/search",
    method="GET",
    schema=LogSearchQuerySerializer,
    inject="team_list_with_user",
    permission="search-View",
    permission_app="log",
    summary=f"检索日志，时间窗最长 1 小时，单次最多 100 条，正文截断（{_ORG_SCOPE}）",
)
def openapi_search_logs(log_group_id, start, end, query="*", limit=20, *, team=None, user_info=None):
    del user_info
    return search_logs(
        team=team,
        log_group_id=log_group_id,
        start=start,
        end=end,
        query=query,
        limit=limit,
    )


@openapi_expose(
    path="log/collect-types",
    method="GET",
    schema=LogCollectTypeQuerySerializer,
    inject="team_list_with_user",
    permission="integration_list-View",
    permission_app="log",
    summary=f"分页查询日志采集类型及接入要填写的字段（{_ORG_SCOPE}）",
)
def openapi_list_collect_types(page=1, page_size=20, keyword="", *, team=None, user_info=None):
    del user_info
    return list_collect_types(team=team, page=page, page_size=page_size, keyword=keyword)


@openapi_expose(
    path="log/collect-instances",
    method="POST",
    schema=LogCollectInstanceCreateSerializer,
    inject="team_list_with_user",
    permission="integration_configure-Add",
    permission_app="log",
    summary=f"在本组织节点上创建日志采集实例和配置并下发（{_ORG_SCOPE}）",
)
def openapi_create_collect_instances(collect_type_id, instances, configs=None, *, team=None, user_info=None):
    del user_info
    return create_collect_instances(team=team, collect_type_id=collect_type_id, instances=instances, configs=configs)


@openapi_expose(
    path="log/collect-instances/config",
    method="PUT",
    schema=LogCollectConfigUpdateSerializer,
    inject="team_list_with_user",
    permission="integration_configure-Add",
    permission_app="log",
    summary=f"修改本组织日志采集配置并重新下发（{_ORG_SCOPE}）",
)
def openapi_update_collect_config(instance_id, collect_type_id, child=None, base=None, *, team=None, user_info=None):
    del user_info
    return update_collect_config(
        team=team,
        instance_id=instance_id,
        collect_type_id=collect_type_id,
        child=child,
        base=base,
    )


@openapi_expose(
    path="log/collect-instances",
    method="DELETE",
    schema=LogCollectInstanceDeleteSerializer,
    inject="team_list_with_user",
    permission="integration_configure-Add",
    permission_app="log",
    summary=f"移除本组织日志采集实例及其配置（{_ORG_SCOPE}）",
)
def openapi_delete_collect_instances(instance_ids, *, team=None, user_info=None):
    del user_info
    return delete_collect_instances(team=team, instance_ids=instance_ids)


@openapi_expose(
    path="log/k8s-collectors",
    method="POST",
    schema=LogK8sCollectorCreateSerializer,
    inject="team_list_with_user",
    permission="integration_configure-Add",
    permission_app="log",
    summary=f"在日志 Kubernetes 接入向导中创建采集实例（{_ORG_SCOPE}）",
)
def openapi_create_k8s_collector(collect_type_id, name, instance_id=None, *, team=None, user_info=None):
    del user_info
    return create_k8s_collector(team=team, collect_type_id=collect_type_id, name=name, instance_id=instance_id)


@openapi_expose(
    path="log/k8s-collectors/setting",
    method="PUT",
    schema=LogK8sSettingSerializer,
    inject="team_list_with_user",
    permission="integration_configure-Add",
    permission_app="log",
    summary=f"保存日志 Kubernetes 采集范围，例如命名空间和容器日志路径（{_ORG_SCOPE}）",
)
def openapi_save_k8s_setting(
    instance_id,
    runtime_profile,
    host_log_path="",
    docker_container_log_path="",
    namespace_patterns="",
    pod_patterns="",
    tolerations=None,
    *,
    team=None,
    user_info=None,
):
    del user_info
    setting = {
        "runtime_profile": runtime_profile,
        "host_log_path": host_log_path,
        "docker_container_log_path": docker_container_log_path,
        "namespace_patterns": namespace_patterns,
        "pod_patterns": pod_patterns,
    }
    if tolerations is not None:
        setting["tolerations"] = tolerations
    return save_k8s_setting(team=team, instance_id=instance_id, **setting)


@openapi_expose(
    path="log/k8s-collectors/install-command",
    method="POST",
    schema=LogK8sInstallCommandSerializer,
    inject="team_list_with_user",
    permission="integration_configure-Add",
    permission_app="log",
    summary=f"生成复制到集群执行的日志采集安装命令（{_ORG_SCOPE}）",
)
def openapi_k8s_install_command(
    instance_id,
    cloud_region_id,
    image_registry_prefix=None,
    tolerations=None,
    *,
    team=None,
    user_info=None,
):
    del user_info
    return k8s_install_command(
        team=team,
        instance_id=instance_id,
        cloud_region_id=cloud_region_id,
        image_registry_prefix=image_registry_prefix,
        tolerations=tolerations,
    )


@openapi_expose(
    path="log/k8s-collectors/status",
    method="GET",
    schema=LogK8sStatusQuerySerializer,
    inject="team_list_with_user",
    permission="integration_list-View",
    permission_app="log",
    summary=f"检查日志 Kubernetes 采集是否已经上报（{_ORG_SCOPE}）",
)
def openapi_k8s_status(instance_id, *, team=None, user_info=None):
    del user_info
    return k8s_status(team=team, instance_id=instance_id)
