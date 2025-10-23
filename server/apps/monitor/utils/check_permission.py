def check_permission(monitor_object_id, instance_id, teams, permissions, cur_team):

    # 超管，校验实例是否处于当前组
    admin_cur_team = permissions.get("all", {}).get("team")
    if admin_cur_team:
        if teams & set(admin_cur_team):
            return True

    cur_team = set(cur_team)

    # 普通用户，未设置实例权限时，根据当前组判断
    permission = permissions.get(monitor_object_id)
    if not permission:
        if cur_team & teams:
            # 此实例组织在当前组中，有权限
            return True
        else:
            # 此实例组织不在当前组，无权限
            return False

    inst_permission = {i["id"] for i in permission.get("instance", [])}
    team_permission = {i["id"] for i in permission.get("team", [])}

    # 存在实例权限，但是都为空时，代表此对象当前组没有任何此类对象的实例权限
    if not inst_permission and not team_permission:
        return False

    # 如果实例权限中包含当前实例ID，直接返回True
    if instance_id in inst_permission:
        return True

    team_permission = set(team_permission)
    # 如果当前组在实例权限中有权限，直接返回True
    if teams & team_permission:
        return True

    return False
