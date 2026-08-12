import uuid

# flake8: noqa
from .common import *  # noqa: F401,F403
from .common import _build_jwt_payload


@nats_client.register
def get_namespace_by_domain(domain):
    # 遗留 bk_lite 域名解析；用户同步迁移至集成中心 user_sync Provider 后移除。
    login_module = LoginModule.objects.filter(source_type="bk_lite", other_config__contains={"domain": domain}).first()
    if not login_module:
        return {"result": False, "message": "Login module not found"}
    namespace = login_module.other_config.get("namespace", "")
    return {"result": True, "data": namespace}


@nats_client.register
def get_login_module_domain_list():
    # 遗留 bk_lite 域名列表；不再新增基于 LoginModule 的调用方。
    login_module_list = list(LoginModule.objects.filter(source_type="bk_lite").values_list("other_config__domain", flat=True))
    login_module_list.insert(0, "domain.com")
    return {"result": True, "data": login_module_list}


@nats_client.register
def verify_bk_token(bk_token):
    # 遗留蓝鲸平台认证实现。管理入口已关闭，后续应迁移为集成中心 Provider
    # 的 login_auth capability；在替代链路交付前仅保留存量兼容，不新增调用方。
    login_module = LoginModule.objects.filter(source_type="bk_login", enabled=True).first()
    if not login_module:
        return {"result": True, "data": {"bk_login_open": False}}
    bk_config = login_module.decrypted_other_config
    if not bk_token:
        return {
            "result": True,
            "data": {"bk_login_open": True, "user": {}, "url": bk_config.get("bk_url")},
        }
    res, bk_user = get_bk_user_info(
        bk_token,
        bk_config.get("app_id"),
        bk_config.get("app_token"),
        bk_config.get("bk_url"),
    )
    if not res:
        return {
            "result": True,
            "data": {"bk_login_open": True, "user": {}, "url": bk_config.get("bk_url")},
        }
    group_obj = Group.objects.get(name=bk_config.get("root_group", "蓝鲸"), parent_id=0)
    user, _ = User.objects.get_or_create(
        username=bk_user["username"],
        domain=bk_user.get("domain"),
        defaults={
            "user_id": str(uuid.uuid4()),
            "email": bk_user.get("email", ""),
            "group_list": [group_obj.id],
            "locale": bk_user.get("language", "zh-Hans"),
            "timezone": bk_user.get("time_zone", "Asia/Shanghai"),
            "role_list": bk_config.get("default_roles", []),
        },
    )
    user.email = bk_user.get("email", "")
    user.locale = bk_user.get("language", user.locale)
    user.timezone = bk_user.get("time_zone", user.timezone)
    user.save()
    user_obj = _build_jwt_payload(user.id)
    secret_key = os.getenv("SECRET_KEY")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    token = jwt.encode(payload=user_obj, key=secret_key, algorithm=algorithm)
    return {
        "result": True,
        "data": {
            "bk_login_open": True,
            "user": {
                "token": token,
                "username": user.username,
                "display_name": user.display_name,
                "id": user.id,
                "user_id": user.user_id,
                "domain": user.domain,
                "locale": user.locale,
                "timezone": user.timezone,
                "qrcode": user.otp_secret is None or user.otp_secret == "",
            },
            "url": bk_config.get("bk_url"),
        },
    }
