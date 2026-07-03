# flake8: noqa
"""Compatibility exports for system_mgmt NATS handlers.

Handlers live in apps.system_mgmt.nats and are imported here so older tests and
callers using apps.system_mgmt.nats_api keep working.
"""

from importlib import import_module

from apps.system_mgmt.nats import *  # noqa: F401,F403


_auth = import_module("apps.system_mgmt.nats.auth")
_channels = import_module("apps.system_mgmt.nats.channels")
_login = import_module("apps.system_mgmt.nats.login")
_otp = import_module("apps.system_mgmt.nats.otp")
_settings = import_module("apps.system_mgmt.nats.settings")
_wechat = import_module("apps.system_mgmt.nats.wechat")


_COMPAT_GLOBALS_BY_MODULE = {
    _auth: (
        "_verify_token",
        "get_user_all_roles",
    ),
    _login: (
        "_verify_token",
        "_build_jwt_payload",
        "_get_pwd_policy_settings",
        "create_challenge",
    ),
    _otp: (
        "_build_jwt_payload",
        "_get_pwd_policy_settings",
        "check_rate_limit",
        "invalidate_challenge",
        "record_failed_attempt",
        "reset_rate_limit",
        "verify_challenge",
    ),
    _settings: (
        "_build_jwt_payload",
        "get_bk_user_info",
    ),
    _wechat: (
        "_build_jwt_payload",
        "set_opspilot_guest_group_default_rule",
    ),
}


def _sync_compat_globals():
    _channels.send_nats_message = send_nats_message
    _channels._normalize_nats_content = _normalize_nats_content

    for module, names in _COMPAT_GLOBALS_BY_MODULE.items():
        for name in names:
            if name in globals():
                setattr(module, name, globals()[name])


def get_pilot_permission_by_token(*args, **kwargs):
    _sync_compat_globals()
    return _auth.get_pilot_permission_by_token(*args, **kwargs)


def verify_token(*args, **kwargs):
    _sync_compat_globals()
    return _auth.verify_token(*args, **kwargs)


def send_msg_with_channel(*args, **kwargs):
    _sync_compat_globals()
    return _channels.send_msg_with_channel(*args, **kwargs)


def login(*args, **kwargs):
    _sync_compat_globals()
    return _login.login(*args, **kwargs)


def reset_pwd(*args, **kwargs):
    _sync_compat_globals()
    return _login.reset_pwd(*args, **kwargs)


def bk_lite_user_login(*args, **kwargs):
    _sync_compat_globals()
    return _login.bk_lite_user_login(*args, **kwargs)


def get_user_login_token(*args, **kwargs):
    _sync_compat_globals()
    return _login.get_user_login_token(*args, **kwargs)


def verify_otp_login(*args, **kwargs):
    _sync_compat_globals()
    return _otp.verify_otp_login(*args, **kwargs)


def verify_bk_token(*args, **kwargs):
    _sync_compat_globals()
    return _settings.verify_bk_token(*args, **kwargs)


def wechat_user_register(*args, **kwargs):
    _sync_compat_globals()
    return _wechat.wechat_user_register(*args, **kwargs)
