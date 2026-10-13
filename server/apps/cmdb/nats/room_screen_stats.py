"""机房大屏统计的 NATS 入口。业务计算在 room_screen_stats 服务。"""

import nats_client


def _caller_context(user_info):
    from apps.cmdb.nats import nats as cmdb_nats

    context = user_info or {}
    return {
        "permission_map": cmdb_nats._build_nats_permission_map(context),
        "user": cmdb_nats._normalize_permission_user(context.get("user"), domain=context.get("domain")),
        "language": cmdb_nats._resolve_nats_cmdb_language(context),
        "parse_locator": cmdb_nats._parse_room3d_server_room_locator,
        "user_info": context,
    }


@nats_client.register
def get_room_device_type_distribution(server_room_id=None, user_info=None, **kwargs):
    """机房内经机柜挂载的可见设备，按模型显示名计数。"""
    from apps.cmdb.services.room_screen_stats import room_device_type_distribution

    context = _caller_context(user_info)
    return room_device_type_distribution(
        server_room_id=server_room_id if server_room_id is not None else kwargs.get("server_room_id"),
        user_info=context["user_info"],
        permission_map=context["permission_map"],
        user=context["user"],
        language=context["language"],
        parse_locator=context["parse_locator"],
    )


@nats_client.register
def get_room_rack_capacity(server_room_id=None, view=None, limit=None, user_info=None, **kwargs):
    """机房机柜容量。summary 为扁平对象，rack_top 为使用率降序。"""
    from apps.cmdb.services.room_screen_stats import room_rack_capacity

    context = _caller_context(user_info)
    return room_rack_capacity(
        server_room_id=server_room_id if server_room_id is not None else kwargs.get("server_room_id"),
        view=view if view is not None else kwargs.get("view"),
        limit=limit if limit is not None else kwargs.get("limit"),
        user_info=context["user_info"],
        permission_map=context["permission_map"],
        user=context["user"],
        parse_locator=context["parse_locator"],
    )


@nats_client.register
def get_room_active_alarms(
    server_room_id=None,
    view=None,
    limit=None,
    user_info=None,
    **kwargs,
):
    """机房内经机柜挂载的可见设备的监控覆盖、告警等级、机柜告警和告警设备。"""
    from apps.cmdb.services.room_screen_stats import room_active_alarms

    context = _caller_context(user_info)
    return room_active_alarms(
        server_room_id=server_room_id if server_room_id is not None else kwargs.get("server_room_id"),
        view=view if view is not None else kwargs.get("view"),
        limit=limit if limit is not None else kwargs.get("limit"),
        user_info=context["user_info"],
        permission_map=context["permission_map"],
        user=context["user"],
        language=context["language"],
        parse_locator=context["parse_locator"],
    )
