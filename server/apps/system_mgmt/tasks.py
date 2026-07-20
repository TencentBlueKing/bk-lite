import uuid
from datetime import timedelta

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.utils import timezone as django_timezone

from apps.core.logger import system_mgmt_logger as logger
from apps.core.utils.permission_cache import clear_users_permission_cache
from apps.rpc.base import RpcClient
from apps.system_mgmt.models import Channel, ErrorLog, Group, LoginModule, SystemSettings, User
from apps.system_mgmt.models.channel import ChannelChoices
from apps.system_mgmt.utils.channel_utils import send_email_to_user


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def write_error_log_async(self, username, app, module, error_message, domain, stack_trace):
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
        ErrorLog.objects.create(username=username, app=app, module=module, error_message=error_message, domain=domain, stack_trace=stack_trace)
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
        return result
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
                "user_id": str(uuid.uuid4()),
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
        clear_users_permission_cache([{"username": user.username, "domain": user.domain} for user in update_users])
        logger.info(f"Updated {len(update_users)} existing users")

    return list(user_data_map.keys())


@shared_task
def check_password_expiry_and_notify():
    """
    定时检查密码即将过期的用户，通过邮件通道发送提醒。
    由 Celery Beat 每天 09:00 调度执行。
    """

    logger.info("== 开始检查密码过期提醒 ==")

    # 读取密码策略配置
    validity_setting = SystemSettings.objects.filter(key="pwd_set_validity_period").first()
    validity_days = int(validity_setting.value) if validity_setting else 180

    # validity_days <= 0 表示永不过期，跳过过期检查
    if validity_days <= 0:
        logger.info("密码有效期设置为永不过期，跳过过期提醒")
        return {"result": True, "message": "Password never expires, skipping reminder"}

    reminder_setting = SystemSettings.objects.filter(key="pwd_set_expiry_reminder_days").first()
    reminder_days = int(reminder_setting.value) if reminder_setting else 7

    # 获取邮件通道
    channel_obj = Channel.objects.filter(channel_type=ChannelChoices.EMAIL).first()
    if not channel_obj:
        logger.warning("未配置邮件通道，跳过密码过期提醒")
        return {"result": False, "message": "No email channel configured"}

    channel_config = channel_obj.config.copy()
    channel_obj.decrypt_field("smtp_pwd", channel_config)

    now = django_timezone.now()
    notified = 0
    skipped = 0

    # 查询所有启用且有密码修改记录的用户
    users = User.objects.filter(disabled=False, password_last_modified__isnull=False).exclude(email="")

    for user in users:
        expire_date = user.password_last_modified + timedelta(days=validity_days)
        days_left = (expire_date - now).days

        if days_left > reminder_days:
            continue

        if days_left > 0:
            subject = "密码即将过期提醒"
            body = f"<p>尊敬的 {user.display_name or user.username}：</p><p>您的密码将在 <b>{days_left}</b> 天后过期，请尽快修改密码。</p>"
        else:
            subject = "密码已过期提醒"
            body = f"<p>尊敬的 {user.display_name or user.username}：</p><p>您的密码已过期，请立即修改密码。</p>"

        result = send_email_to_user(channel_config, body, [user.email], subject)
        if result.get("result"):
            notified += 1
            logger.info(f"密码过期提醒已发送: {user.username}@{user.domain}, 剩余{days_left}天")
        else:
            skipped += 1
            logger.error(f"密码过期提醒发送失败: {user.username}@{user.domain}, {result.get('message')}")

    logger.info(f"== 密码过期提醒完成 == 通知={notified}, 失败={skipped}")
    return {"result": True, "notified": notified, "failed": skipped}


@shared_task
def execute_user_sync_source(source_id, trigger_mode="manual"):
    from apps.system_mgmt.services.user_sync_service import execute_user_sync

    return execute_user_sync(int(source_id), trigger_mode)


@shared_task
def schedule_im_notification_sync(channel_id):
    from apps.system_mgmt.services.im_notification_service import create_im_notification_sync_run

    result = create_im_notification_sync_run(int(channel_id), trigger_mode="schedule")
    if not result.get("result"):
        logger.info(f"Skip scheduled IM notification sync for channel {channel_id}: {result.get('message', '')}")
        return result

    run_id = result["data"]["run_id"]
    execute_im_notification_sync_run_task.delay(run_id)
    return result


@shared_task
def execute_im_notification_sync_run_task(run_id):
    from apps.system_mgmt.services.im_notification_service import execute_im_notification_sync_run

    return execute_im_notification_sync_run(int(run_id))


# ---------------------------------------------------------------------------
# 用户同步-本地密码初始化: 初始密码邮件发送(Task 3 完整实现)
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def send_initial_password_email(self, user_id, run_id):
    """
    Celery worker 端:
      1. 取 user + run
      2. 解密 vault 拿 raw_password
      3. 调 RuntimeApplicationService 发送邮件
      4. 成功后原子地 pop vault + 回写 email_status
      5. 失败重试 3 次，最终失败才原子标记 failed
    """
    from apps.system_mgmt.models import User as UserModel
    from apps.system_mgmt.models import UserSyncRun as UserSyncRunModel
    from apps.system_mgmt.nats.email_status import complete_password_email_delivery
    from apps.system_mgmt.services.password_init_email import send_email_via_runtime
    from apps.system_mgmt.utils.password_vault import decrypt_from_vault

    user = UserModel.objects.filter(id=user_id).first()
    run = UserSyncRunModel.objects.filter(id=run_id).first()
    if not user or not run:
        logger.error(f"send_initial_password_email user={user_id} run={run_id} 数据缺失")
        return

    username = user.username
    encrypted = (run.payload or {}).get("password_vault", {}).get(username)
    if not encrypted:
        logger.warning(f"vault 缺 username={username},run={run_id} 已发送或丢失")
        return

    try:
        raw_password = decrypt_from_vault(encrypted)
    except Exception as e:
        logger.error(f"vault 解密失败 user={username} run={run_id}: {e}")
        complete_password_email_delivery(run_id, username, ok=False, reason="vault 解密失败")
        return

    try:
        result = send_email_via_runtime(user, raw_password)
    except Exception as exc:
        logger.warning(f"邮件发送异常 username={username}: {exc};触发重试")
        _retry_or_complete_failure(self, run_id, username, str(exc), exc)
        return

    if result.get("result"):
        complete_password_email_delivery(run_id, username, ok=True)
    else:
        msg = result.get("message", "未知错误")
        _retry_or_complete_failure(self, run_id, username, msg, Exception(msg))


def _retry_or_complete_failure(task, run_id, username, reason, exc):
    """重试未耗尽时让 Retry 冒泡；耗尽后才完成失败状态。"""
    from apps.system_mgmt.nats.email_status import complete_password_email_delivery

    try:
        task.retry(exc=exc)
    except MaxRetriesExceededError:
        complete_password_email_delivery(run_id, username, ok=False, reason=reason)


@shared_task
def send_initial_password_email_batch(run_id: int):
    """领取一批待投递用户，在单条 SMTP 会话中发送个性化初始密码邮件。"""
    from apps.system_mgmt.models import User as UserModel
    from apps.system_mgmt.models import UserSyncRun as UserSyncRunModel
    from apps.system_mgmt.nats.email_status import claim_password_email_batch, complete_password_email_batch
    from apps.system_mgmt.services.password_init_email import send_initial_password_emails
    from apps.system_mgmt.utils.password_vault import decrypt_from_vault

    claimed = claim_password_email_batch(run_id)
    if not claimed:
        return
    run = UserSyncRunModel.objects.filter(id=run_id).select_related("source").first()
    if not run:
        return
    users = {user.id: user for user in UserModel.objects.filter(id__in=[item["user_id"] for item in claimed])}
    deliveries, outcomes = [], []
    vault = (run.payload or {}).get("password_vault", {})
    for item in claimed:
        username = item["username"]
        user = users.get(item["user_id"])
        if not user or not user.email:
            outcomes.append({"username": username, "ok": False, "reason": "用户邮箱为空或用户不存在"})
            continue
        try:
            raw_password = decrypt_from_vault(vault[username])
        except Exception:
            outcomes.append({"username": username, "ok": False, "reason": "vault 解密失败"})
            continue
        deliveries.append({"user": user, "username": username, "raw_password": raw_password})
    if deliveries:
        results = send_initial_password_emails(run.source, deliveries)
        outcomes.extend({"username": item["username"], "ok": bool(results.get(item["username"], {}).get("result")), "reason": results.get(item["username"], {}).get("message", "邮件发送失败")} for item in deliveries)
    has_pending = complete_password_email_batch(run_id, outcomes)
    if has_pending:
        send_initial_password_email_batch.delay(run_id)


@shared_task
def recover_stuck_initial_password_email_batches():
    """Beat 兜底回收 Worker 中断时遗留的邮件投递租约。"""
    from datetime import timedelta

    from django.utils import timezone

    from apps.system_mgmt.models import UserSyncRun as UserSyncRunModel
    from apps.system_mgmt.nats.email_status import recover_expired_password_email_batch

    recovered_runs = 0
    for run_id in UserSyncRunModel.objects.filter(started_at__gte=timezone.now() - timedelta(days=1)).values_list("id", flat=True):
        if recover_expired_password_email_batch(run_id):
            send_initial_password_email_batch.delay(run_id)
            recovered_runs += 1
    return {"recovered_runs": recovered_runs}
