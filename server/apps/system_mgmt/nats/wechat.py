# flake8: noqa
from .common import *  # noqa: F401,F403
from .users import set_opspilot_guest_group_default_rule


@nats_client.register
def wechat_user_register(user_id, nick_name):
    with transaction.atomic():
        user, is_first_login = User.objects.select_for_update().get_or_create(
            username=user_id, defaults={"display_name": nick_name}
        )
        default_group = Group.objects.filter(name="OpsPilotGuest", parent_id=0).first()
        if not user.group_list and default_group:
            user.group_list = [default_group.id]
        default_role = list(
            Role.objects.filter(
                Q(name="normal", app__in=["opspilot", "ops-console"])
                | Q(
                    name="guest",
                    app__in=["opspilot", "cmdb", "monitor", "log", "alarm", "node", "mlops", "job"],
                )
            ).values_list("id", flat=True)
        )
        default_role.extend(user.role_list)
        user.role_list = list(set(default_role))
        user.last_login = timezone.now()
        user.save()
    try:
        if default_group:
            set_opspilot_guest_group_default_rule(default_group, user)
    except Exception:  # noqa
        pass
    secret_key = os.getenv("SECRET_KEY")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    user_obj = _build_jwt_payload(user.id)
    token = jwt.encode(payload=user_obj, key=secret_key, algorithm=algorithm)
    return {
        "result": True,
        "data": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "is_first_login": is_first_login,
            "locale": user.locale,
            "timezone": user.timezone,
            "token": token,
        },
    }


@nats_client.register
def get_wechat_settings():
    login_module = LoginModule.objects.filter(source_type="wechat", enabled=True).first()
    if not login_module:
        return {"result": True, "data": {"enabled": False}}

    return {
        "result": True,
        "data": {
            "enabled": True,
            "app_id": login_module.app_id,
            # app_secret 不再返回给前端，OAuth 验证已移至后端
            "redirect_uri": login_module.other_config.get("redirect_uri", ""),
            "callback_url": login_module.other_config.get("callback_url", ""),
        },
    }
