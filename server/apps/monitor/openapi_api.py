"""监控统一 OpenAPI 网关端点。"""

from apps.core.openapi.decorators import openapi_expose
from apps.monitor.openapi_serializers import (
    MonitorClusterCollectorCreateSerializer,
    MonitorClusterInstallCommandSerializer,
    MonitorClusterStatusQuerySerializer,
    MonitorInstanceQuerySerializer,
    MonitorIntegrationCreateSerializer,
    MonitorIntegrationDeleteSerializer,
    MonitorMetricQuerySerializer,
    MonitorMetricRangeQuerySerializer,
    MonitorMetricValueQuerySerializer,
    MonitorObjectQuerySerializer,
    MonitorPluginFormQuerySerializer,
    MonitorPluginQuerySerializer,
    MonitorPolicyGroupQuerySerializer,
    MonitorPolicyQuerySerializer,
)
from apps.monitor.openapi_service import (
    cluster_install_command,
    cluster_status,
    create_cluster_collector,
    create_integration,
    delete_integrations,
    get_plugin_form,
    list_instances,
    list_metrics,
    list_objects,
    list_plugins,
    list_policies,
    list_policy_groups,
    query_metric_instant,
    query_metric_range,
)

_ORG_SCOPE = "组织口径：API 令牌绑定组织精确匹配，不级联子组织"
_CATALOG_SCOPE = "监控对象是平台目录，各组织看到同一份可见对象；调用仍须绑定组织"


@openapi_expose(
    path="monitor/objects",
    method="GET",
    schema=MonitorObjectQuerySerializer,
    inject="team_list_with_user",
    permission="object-View",
    permission_app="monitor",
    summary=f"分页查询可见监控对象（{_CATALOG_SCOPE}）",
)
def openapi_list_objects(page=1, page_size=20, keyword="", *, team=None, user_info=None):
    del user_info
    return list_objects(team=team, page=page, page_size=page_size, keyword=keyword)


@openapi_expose(
    path="monitor/instances",
    method="GET",
    schema=MonitorInstanceQuerySerializer,
    inject="team_list_with_user",
    permission="asset-View",
    permission_app="monitor",
    summary=f"分页查询监控实例（{_ORG_SCOPE}）",
)
def openapi_list_instances(
    page=1,
    page_size=20,
    keyword="",
    monitor_object_id=None,
    *,
    team=None,
    user_info=None,
):
    del user_info
    return list_instances(
        team=team,
        page=page,
        page_size=page_size,
        keyword=keyword,
        monitor_object_id=monitor_object_id,
    )


@openapi_expose(
    path="monitor/policies",
    method="GET",
    schema=MonitorPolicyQuerySerializer,
    inject="team_list_with_user",
    permission="strategy_list-View",
    permission_app="monitor",
    summary=f"分页查询监控策略，不含策略组内规则（{_ORG_SCOPE}）",
)
def openapi_list_policies(
    page=1,
    page_size=20,
    keyword="",
    monitor_object_id=None,
    *,
    team=None,
    user_info=None,
):
    del user_info
    return list_policies(
        team=team,
        page=page,
        page_size=page_size,
        keyword=keyword,
        monitor_object_id=monitor_object_id,
    )


@openapi_expose(
    path="monitor/metrics",
    method="GET",
    schema=MonitorMetricQuerySerializer,
    inject="team_list_with_user",
    permission="view_list-View",
    permission_app="monitor",
    summary=f"分页查询监控对象的指标定义，不含查询语句（{_ORG_SCOPE}）",
)
def openapi_list_metrics(
    page=1,
    page_size=20,
    keyword="",
    monitor_object_id=None,
    *,
    team=None,
    user_info=None,
):
    del user_info
    return list_metrics(
        team=team,
        page=page,
        page_size=page_size,
        keyword=keyword,
        monitor_object_id=monitor_object_id,
    )


@openapi_expose(
    path="monitor/metrics/instant",
    method="GET",
    schema=MonitorMetricValueQuerySerializer,
    inject="team_list_with_user",
    permission="view_list-View",
    permission_app="monitor",
    summary=f"查询监控实例的指标当前值（{_ORG_SCOPE}）",
)
def openapi_query_metric_instant(instance_id, metric_id, *, team=None, user_info=None):
    del user_info
    return query_metric_instant(team=team, instance_id=instance_id, metric_id=metric_id)


@openapi_expose(
    path="monitor/metrics/range",
    method="GET",
    schema=MonitorMetricRangeQuerySerializer,
    inject="team_list_with_user",
    permission="view_list-View",
    permission_app="monitor",
    summary=f"查询监控实例的指标曲线，时间窗最长 6 小时（{_ORG_SCOPE}）",
)
def openapi_query_metric_range(
    instance_id,
    metric_id,
    start,
    end,
    step="5m",
    *,
    team=None,
    user_info=None,
):
    del user_info
    return query_metric_range(
        team=team,
        instance_id=instance_id,
        metric_id=metric_id,
        start=start,
        end=end,
        step=step,
    )


@openapi_expose(
    path="monitor/plugins",
    method="GET",
    schema=MonitorPluginQuerySerializer,
    inject="team_list_with_user",
    permission="integration_list-View",
    permission_app="monitor",
    summary=f"分页查询监控对象下可接入的插件（{_CATALOG_SCOPE}）",
)
def openapi_list_plugins(page=1, page_size=20, keyword="", monitor_object_id=None, *, team=None, user_info=None):
    del user_info
    return list_plugins(team=team, page=page, page_size=page_size, keyword=keyword, monitor_object_id=monitor_object_id)


@openapi_expose(
    path="monitor/plugins/form",
    method="GET",
    schema=MonitorPluginFormQuerySerializer,
    inject="team_list_with_user",
    permission="integration_configure-View",
    permission_app="monitor",
    summary=f"查询插件接入配置页要填写的采集参数，不含查询语句（{_CATALOG_SCOPE}）",
)
def openapi_get_plugin_form(plugin_id, *, team=None, user_info=None):
    del user_info
    return get_plugin_form(team=team, plugin_id=plugin_id)


@openapi_expose(
    path="monitor/policy-groups",
    method="GET",
    schema=MonitorPolicyGroupQuerySerializer,
    inject="team_list_with_user",
    permission="strategy_list-View",
    permission_app="monitor",
    summary=f"分页查询监控对象在本组织下的策略组，只读且不创建默认组（{_ORG_SCOPE}）",
)
def openapi_list_policy_groups(
    page=1,
    page_size=20,
    keyword="",
    monitor_object_id=None,
    plugin_id=None,
    *,
    team=None,
    user_info=None,
):
    del user_info
    return list_policy_groups(
        team=team,
        page=page,
        page_size=page_size,
        keyword=keyword,
        monitor_object_id=monitor_object_id,
        plugin_id=plugin_id,
    )


@openapi_expose(
    path="monitor/integrations",
    method="POST",
    schema=MonitorIntegrationCreateSerializer,
    inject="team_list_with_user",
    permission="integration_configure-Add",
    permission_app="monitor",
    summary=f"保存主机、SNMP 或脚本接入：创建实例、写入采集参数、按选择加入策略组并下发（{_ORG_SCOPE}）",
)
def openapi_create_integration(
    monitor_object_id,
    monitor_plugin_id,
    instances,
    configs=None,
    policy_group=None,
    credential=None,
    *,
    team=None,
    user_info=None,
):
    return create_integration(
        team=team,
        user_info=user_info,
        monitor_object_id=monitor_object_id,
        monitor_plugin_id=monitor_plugin_id,
        instances=instances,
        configs=configs,
        policy_group=policy_group,
        credential=credential,
    )


@openapi_expose(
    path="monitor/integrations",
    method="DELETE",
    schema=MonitorIntegrationDeleteSerializer,
    inject="team_list_with_user",
    permission="asset-Delete",
    permission_app="monitor",
    summary=f"删除本组织的监控接入实例及其采集配置（{_ORG_SCOPE}）",
)
def openapi_delete_integrations(instance_ids, *, team=None, user_info=None):
    return delete_integrations(team=team, user_info=user_info, instance_ids=instance_ids)


@openapi_expose(
    path="monitor/cluster-collectors",
    method="POST",
    schema=MonitorClusterCollectorCreateSerializer,
    inject="team_list_with_user",
    permission="integration_configure-Add",
    permission_app="monitor",
    summary=f"在 Kubernetes 或 K3s 接入向导中创建采集实例，collector_type 取 kubernetes 或 k3s（{_ORG_SCOPE}）",
)
def openapi_create_cluster_collector(
    collector_type,
    monitor_object_id,
    name,
    instance_id,
    interval=None,
    *,
    team=None,
    user_info=None,
):
    return create_cluster_collector(
        team=team,
        user_info=user_info,
        collector_type=collector_type,
        monitor_object_id=monitor_object_id,
        name=name,
        instance_id=instance_id,
        interval=interval,
    )


@openapi_expose(
    path="monitor/cluster-collectors/install-command",
    method="POST",
    schema=MonitorClusterInstallCommandSerializer,
    inject="team_list_with_user",
    permission="integration_configure-Add",
    permission_app="monitor",
    summary=f"生成复制到集群执行的安装命令；k3s 同时返回卸载命令，且不接受镜像仓库前缀和容忍度（{_ORG_SCOPE}）",
)
def openapi_cluster_install_command(
    collector_type,
    instance_id,
    cloud_region_id,
    image_registry_prefix=None,
    tolerations=None,
    *,
    team=None,
    user_info=None,
):
    del user_info
    return cluster_install_command(
        team=team,
        collector_type=collector_type,
        instance_id=instance_id,
        cloud_region_id=cloud_region_id,
        image_registry_prefix=image_registry_prefix,
        tolerations=tolerations,
    )


@openapi_expose(
    path="monitor/cluster-collectors/status",
    method="GET",
    schema=MonitorClusterStatusQuerySerializer,
    inject="team_list_with_user",
    permission="integration_configure-View",
    permission_app="monitor",
    summary=f"检查 Kubernetes 或 K3s 采集是否已经上报；kubernetes 要带监控对象（{_ORG_SCOPE}）",
)
def openapi_cluster_status(collector_type, instance_id, monitor_object_id=None, *, team=None, user_info=None):
    del user_info
    return cluster_status(
        team=team,
        collector_type=collector_type,
        instance_id=instance_id,
        monitor_object_id=monitor_object_id,
    )
