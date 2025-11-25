from celery import shared_task

from apps.core.logger import system_mgmt_logger as logger
from apps.rpc.base import RpcClient
from apps.system_mgmt.models import ErrorLog, Group, LoginModule, User


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def write_error_log_async(self, username, app, module, error_message, domain):
    """
    异步写入错误日志到数据库

    Args:
        username: 用户名
        app: 应用名称
        module: 模块名称
        error_message: 错误信息
        domain: 域名

    Returns:
        dict: 执行结果
    """
    try:
        ErrorLog.objects.create(
            username=username,
            app=app,
            module=module,
            error_message=error_message,
            domain=domain,
        )
        logger.debug(f"Successfully logged error for {username}@{domain} in {app}/{module}")
        return {"result": True, "message": "Error log written successfully"}
    except Exception as exc:
        logger.error(f"Failed to write error log: {str(exc)}")
        # 重试机制：最多重试3次
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for writing error log: {username}@{domain}")
            return {"result": False, "message": "Failed to write error log after retries"}


@shared_task
def sync_user_and_group_by_login_module(login_module_id):
    login_module = LoginModule.objects.filter(id=login_module_id, enabled=True).first()
    if not login_module:
        return {"result": False, "message": "Login module not found or not enabled."}
    logger.info(f"Syncing user and group for login module {login_module_id} - {login_module.name}")
    namespace = login_module.other_config.get("namespace", "")
    client = RpcClient(namespace)
    result = client.request("sync_data")
    if not result["result"]:
        logger.error(f"Failed to sync data for login module {login_module_id}: {result['message']}")
    user_list = result["data"]["user_list"]
    group_list = result["data"]["group_list"]
    sync_user_and_groups(user_list, group_list, login_module)
    logger.info(f"Sync completed for login module {login_module_id} - {login_module.name}")


def sync_user_and_groups(user_list, group_list, login_module):
    """同步用户和组数据到本地数据库"""
    try:
        parent_group, _ = Group.objects.get_or_create(
            name=login_module.other_config.get("root_group", login_module.name),
            parent_id=0,
            defaults={"description": login_module.name + "_bk_lite"},
        )
        domain = login_module.other_config.get("domain")
        group_id_mapping = _sync_groups(group_list, parent_group, None)
        logger.info(f"Successfully {len(group_id_mapping)} groups")
        default_role = login_module.other_config.get("default_roles", [])
        synced_users = _sync_users(user_list, group_id_mapping, domain, default_role)
        logger.info(f"Successfully synced {len(synced_users)} users")
        return {"result": True, "data": {"synced_users": len(synced_users), "synced_groups": len(group_id_mapping)}}
    except Exception as e:
        logger.exception(f"Error syncing users and groups: {e}")
        return {"result": False, "message": str(e)}


def _sync_groups(group_list, parent_group, parent_group_id):
    """同步组数据并返回ID映射"""
    group_id_mapping = {}

    # 获取当前层级的子组
    children = {i["id"]: i for i in group_list if i["parent_id"] == parent_group_id}

    # 获取已存在的组
    existing_groups = Group.objects.filter(parent_id=parent_group.id)
    exist_groups_by_external_id = {i.external_id: i for i in existing_groups if i.external_id}
    exist_groups_by_name = {i.name: i for i in existing_groups}

    add_groups = []
    update_groups = []
    # 删除未使用的 existing_external_ids 变量
    current_external_ids = set(children.keys())

    # 处理需要删除的组
    delete_groups = [group.id for group in existing_groups if group.external_id and group.external_id not in current_external_ids]
    if delete_groups:
        Group.objects.filter(id__in=delete_groups).delete()
        logger.info(f"Deleted {len(delete_groups)} groups under parent {parent_group.name}")

    # 处理当前层级的组
    for external_id, group_data in children.items():
        group_name = group_data["name"]

        if external_id in exist_groups_by_external_id:
            # 组已存在，添加到映射并递归处理子组
            existing_group = exist_groups_by_external_id[external_id]
            group_id_mapping[external_id] = existing_group.id

            # 更新组名称（如果有变化）
            if existing_group.name != group_name:
                existing_group.name = group_name
                update_groups.append(existing_group)

            # 递归处理子组
            child_mapping = _sync_groups(group_list, existing_group, external_id)
            group_id_mapping.update(child_mapping)

        elif group_name in exist_groups_by_name:
            # 组名存在但没有external_id，更新external_id
            existing_group = exist_groups_by_name[group_name]
            existing_group.external_id = external_id
            update_groups.append(existing_group)
            group_id_mapping[external_id] = existing_group.id

            # 递归处理子组
            child_mapping = _sync_groups(group_list, existing_group, external_id)
            group_id_mapping.update(child_mapping)

        else:
            # 新组，需要创建
            new_group = Group(
                name=group_name,
                parent_id=parent_group.id,
                external_id=external_id,
                description=parent_group.description,
            )
            add_groups.append(new_group)

    # 批量更新组
    if update_groups:
        Group.objects.bulk_update(update_groups, ["name", "external_id"], batch_size=100)
        logger.info(f"Updated {len(update_groups)} groups under parent {parent_group.name}")

    # 批量创建新组
    if add_groups:
        created_groups = Group.objects.bulk_create(add_groups, batch_size=100)
        logger.info(f"Created {len(created_groups)} groups under parent {parent_group.name}")

        # 为新创建的组添加映射并递归处理子组
        for created_group in created_groups:
            external_id = created_group.external_id
            group_id_mapping[external_id] = created_group.id

            # 递归处理子组
            child_mapping = _sync_groups(group_list, created_group, external_id)
            group_id_mapping.update(child_mapping)

    return group_id_mapping


def _update_group_hierarchy(group_list, external_to_name):
    """更新组的层级关系"""
    for group_data in group_list:
        parent_external_id = group_data.get("parent_id")
        if not parent_external_id or parent_external_id not in external_to_name:
            continue

        current_group_name = group_data["name"]
        parent_group_name = external_to_name[parent_external_id]

        try:
            parent_group = Group.objects.get(name=parent_group_name)
            current_group = Group.objects.get(name=current_group_name)

            if current_group.parent_id != parent_group.id:
                current_group.parent_id = parent_group.id
                current_group.save()
                logger.info(f"Updated group hierarchy: {current_group_name} -> {parent_group_name}")
        except Group.DoesNotExist:
            logger.warning(f"Group not found when updating hierarchy: {current_group_name} or {parent_group_name}")


def _sync_users(user_list, group_id_mapping, domain, default_role):
    """同步用户数据"""
    # 构建用户的唯一标识列表
    user_identifiers = []
    user_data_map = {}

    for user_data in user_list:
        username = user_data["username"]
        identifier = f"{username}@{domain}"
        user_identifiers.append(identifier)
        user_data_map[identifier] = user_data

    # 批量查询已存在的用户
    usernames = [uid.split("@")[0] for uid in user_identifiers]
    existing_users = User.objects.filter(username__in=usernames, domain=domain)
    existing_users_dict = {f"{user.username}@{getattr(user, 'domain', '')}": user for user in existing_users}

    existing_user_identifiers = set(existing_users_dict.keys())

    create_users = []
    update_users = []

    for identifier, user_data in user_data_map.items():
        username = user_data["username"]
        local_group_ids = [group_id_mapping[dept_id] for dept_id in user_data.get("departments", []) if dept_id in group_id_mapping]

        if identifier in existing_user_identifiers:
            # 更新已存在的用户
            user_obj = existing_users_dict[identifier]
            user_obj.display_name = user_data.get("display_name", user_obj.display_name)
            user_obj.group_list = local_group_ids
            update_users.append(user_obj)
        else:
            # 创建新用户
            user_defaults = {
                "username": username,
                "display_name": user_data.get("display_name", username),
                "email": user_data.get("email", ""),
                "locale": "zh-Hans",
                "timezone": "Asia/Shanghai",
                "group_list": local_group_ids,
                "password": "",
                "domain": domain,
                "role_list": default_role,
            }
            new_user = User(**user_defaults)
            create_users.append(new_user)

    # 批量创建新用户
    if create_users:
        User.objects.bulk_create(create_users, batch_size=100)
        logger.info(f"Created {len(create_users)} new users")

    # 批量更新已存在的用户
    if update_users:
        update_fields = ["display_name", "group_list"]
        if any(hasattr(user, "domain") for user in update_users):
            update_fields.append("domain")

        User.objects.bulk_update(update_users, update_fields, batch_size=100)
        logger.info(f"Updated {len(update_users)} existing users")

    return list(user_data_map.keys())
