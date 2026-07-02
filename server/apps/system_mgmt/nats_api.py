# flake8: noqa
"""Compatibility exports for system_mgmt NATS handlers.

Handlers live in apps.system_mgmt.nats and are imported here so older tests and
callers using apps.system_mgmt.nats_api keep working.
"""

from apps.system_mgmt.nats import *  # noqa: F401,F403
from apps.system_mgmt.nats import channels as _channels
from apps.system_mgmt.nats import login as _login


def _sync_compat_globals():
    _channels.send_nats_message = send_nats_message
    _channels._normalize_nats_content = _normalize_nats_content
    _login._get_pwd_policy_settings = _get_pwd_policy_settings


def send_msg_with_channel(*args, **kwargs):
    _sync_compat_globals()
    return _channels.send_msg_with_channel(*args, **kwargs)


def login(*args, **kwargs):
    _sync_compat_globals()
    return _login.login(*args, **kwargs)
