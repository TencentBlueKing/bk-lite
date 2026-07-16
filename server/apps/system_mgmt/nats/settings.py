# flake8: noqa
from .common import *  # noqa: F401,F403
from .common import _build_jwt_payload


@nats_client.register
def get_namespace_by_domain(domain):
    login_module = LoginModule.objects.filter(source_type="bk_lite", other_config__contains={"domain": domain}).first()
    if not login_module:
        return {"result": False, "message": "Login module not found"}
    namespace = login_module.other_config.get("namespace", "")
    return {"result": True, "data": namespace}


@nats_client.register
def get_login_module_domain_list():
    login_module_list = list(LoginModule.objects.filter(source_type="bk_lite").values_list("other_config__domain", flat=True))
    login_module_list.insert(0, "domain.com")
    return {"result": True, "data": login_module_list}


@nats_client.register
def verify_bk_token(bk_token):
    login_module = LoginModule.objects.filter(source_type="bk_login", enabled=True).first()
    if not login_module:
        return {"result": True, "data": {"bk_login_open": False}}
    bk_config = login_module.other_config
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
    group_obj = Group.objects.get(name=login_module.other_config.get("root_group", "蓝鲸"), parent_id=0)
    user, _ = User.objects.get_or_create(
        username=bk_user["username"],
        domain=bk_user.get("domain"),
        defaults={
            "email": bk_user.get("email", ""),
            "group_list": [group_obj.id],
            "locale": bk_user.get("language", "zh-Hans"),
            "timezone": bk_user.get("time_zone", "Asia/Shanghai"),
            "role_list": login_module.other_config.get("default_roles", []),
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
