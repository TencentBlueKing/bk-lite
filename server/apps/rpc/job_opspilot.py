"""OpsPilot 与作业平台之间的调用约定。

两边都只依赖这份约定和 NATS。任何一边启动都不会导入对方的模型。
"""

import os
import re
from datetime import datetime

from django.core import signing
from rest_framework.exceptions import PermissionDenied

AUTH_SALT = "apps.job_mgmt.services.opspilot_gateway.v1"
DEFAULT_AUTH_MAX_AGE_SECONDS = 120

ACTION_LIST_SCRIPTS = "list_scripts"
ACTION_LIST_PLAYBOOK_SCRIPTS = "list_playbook_scripts"
ACTION_DESCRIBE_SCRIPT = "describe_script"
ACTION_SEARCH_TARGETS = "search_targets"
ACTION_LIST_TARGETS = "list_targets"
ACTION_EXECUTE = "execute_script"
ACTION_QUERY = "query_execution"
ACTION_DISTRIBUTE = "distribute_files"

_FILE_KEY_RE = re.compile(r"^job-files/\d{4}/\d{2}/\d{2}/[A-Za-z0-9_-]{21}(?:\.[A-Za-z0-9]{1,16})?$")


def _positive_team_id(value) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("team_id must be a positive integer")
    if isinstance(value, str) and not value.isdecimal():
        raise ValueError("team_id must be a positive integer")
    team_id = int(value)
    if team_id <= 0:
        raise ValueError("team_id must be a positive integer")
    return team_id


def _auth_payload(action: str, user_info) -> dict:
    if not isinstance(user_info, dict):
        raise ValueError("user_info must be an object")
    team_id = _positive_team_id(user_info.get("team"))
    username = user_info.get("user")
    domain = user_info.get("domain")
    include_children = user_info.get("include_children")
    if (
        not isinstance(action, str)
        or not action.strip()
        or not isinstance(username, str)
        or not username.strip()
        or not isinstance(domain, str)
        or not domain.strip()
        or type(include_children) is not bool
    ):
        raise ValueError("user_info does not match the job request")
    return {
        "action": action.strip(),
        "team_id": team_id,
        "user": username.strip(),
        "domain": domain.strip(),
        "include_children": include_children,
    }


def sign_opspilot_job_request(action: str, user_info) -> str:
    """签发绑定动作和调用身份的短时令牌。"""

    return signing.dumps(_auth_payload(action, user_info), salt=AUTH_SALT)


def verify_opspilot_job_request(token, action: str, user_info) -> dict:
    """校验令牌、有效期，以及它绑定的动作和调用身份。"""

    try:
        expected = _auth_payload(action, user_info)
        max_age = int(os.getenv("JOB_OPSPILOT_NATS_AUTH_MAX_AGE", DEFAULT_AUTH_MAX_AGE_SECONDS))
        signed = signing.loads(token, salt=AUTH_SALT, max_age=max_age)
    except (signing.BadSignature, TypeError, ValueError):
        raise PermissionDenied("OpsPilot job request authentication failed") from None
    if signed != expected:
        raise PermissionDenied("OpsPilot job request authentication failed")
    return expected


def new_job_file_key(filename: str) -> str:
    """作业文件在 NATS 对象存储上的键。请求消息里只放这个键，不放文件字节。"""

    from nanoid import generate

    safe_name = os.path.basename(str(filename or "").replace("\\", "/")).strip() or "file"
    ext = ""
    if "." in safe_name:
        suffix = safe_name.rsplit(".", 1)[-1]
        if suffix.isalnum() and len(suffix) <= 16:
            ext = "." + suffix
    now = datetime.now()
    return f"job-files/{now.year}/{now.month:02d}/{now.day:02d}/{generate(size=21)}{ext}"


def is_job_file_key(file_key: str) -> bool:
    return isinstance(file_key, str) and _FILE_KEY_RE.fullmatch(file_key) is not None
