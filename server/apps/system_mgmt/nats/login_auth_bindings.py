# flake8: noqa
"""NATS handlers for the login-auth-binding feature.

These handlers drive the third-party login flow that resolves a user via an
external ``LoginAuthBinding`` (e.g. Feishu / WeChat) and then mints a session
token through ``get_user_login_token``. They were moved here from
``apps.system_mgmt.nats_api`` so that the master branch's split-by-domain
NATS layout can stay consistent.
"""

import nats_client

from apps.system_mgmt.services.login_auth_binding_service import (
    get_active_login_auth_bindings,
    login_with_binding as execute_login_with_binding,
    serialize_public_login_auth_binding,
)


@nats_client.register
def login_with_binding(binding_id, auth_code="", username="", password=""):
    return _login_with_binding_service(binding_id, auth_code, username=username, password=password)


def _login_with_binding_service(binding_id, auth_code="", username="", password=""):
    try:
        return execute_login_with_binding(int(binding_id), auth_code, username=username, password=password)
    except (TypeError, ValueError):
        return {"result": False, "message": "Invalid login auth binding id"}


@nats_client.register
def get_login_auth_bindings():
    data = [serialize_public_login_auth_binding(binding) for binding in get_active_login_auth_bindings()]
    return {"result": True, "data": data}