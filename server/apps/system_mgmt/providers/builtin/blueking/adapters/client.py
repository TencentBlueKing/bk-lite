"""本包厂商请求层：蓝鲸 ESB 分页与身份核对。能力模块不要再抄一份。"""

from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml

from apps.system_mgmt.providers.log import logger, safe_exception_info
from apps.system_mgmt.providers.pack_i18n import normalize_locale
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

ALL_DEPARTMENT_ID = "bk_all"
CALLER_USERNAME = "admin"
INVALID_ROOT_DEPARTMENT_IDS = {"", "__all__", "**all**"}
PAGE_SIZE = 2000
TIMEOUT = 10
MAX_PAGES = 100
USER_FIELDS = "username,display_name,email,telephone,departments"
_TRANSPORT_FAILURE_TEMPLATE = "event=blueking_request_failed failed_stage=%s error_type=%s"

LOGIN_GET_USER_PATH = "/api/c/compapi/v2/bk_login/get_user/"
RETRIEVE_USER_PATH = "/api/c/compapi/v2/usermanage/retrieve_user/"
LIST_DEPARTMENTS_PATH = "/api/c/compapi/v2/usermanage/list_departments/"
LIST_USERS_PATH = "/api/c/compapi/v2/usermanage/list_users/"

_LANGUAGE_DIR = Path(__file__).resolve().parent.parent / "language"


def _parse_json_response(response):
    try:
        data = response.json()
    except ValueError:
        raise ValueError("BlueKing response is not valid JSON")
    if not isinstance(data, dict):
        raise ValueError("BlueKing response is not a JSON object")
    return data


def _validate_credentials(config):
    config = config or {}
    for field in ("bk_url", "app_id", "app_token"):
        if not config.get(field):
            return CapabilityExecutionResult.failed_result(
                "BlueKing credentials are incomplete",
                code="provider.invalid_config",
                field=field,
            )
    parsed = urlparse(str(config.get("bk_url") or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return CapabilityExecutionResult.failed_result(
            "BlueKing URL must use HTTP or HTTPS",
            code="provider.invalid_config",
            field="bk_url",
        )
    return None


def _warn_transport_failure(error, error_type):
    logger.warning(
        _TRANSPORT_FAILURE_TEMPLATE,
        "esb_get",
        error_type,
        exc_info=safe_exception_info(error),
    )


def _esb_url(config, path):
    return f"{str(config.get('bk_url') or '').rstrip('/')}{path}"


def _esb_get(config, path, params=None):
    query = {
        "bk_app_code": config.get("app_id"),
        "bk_app_secret": config.get("app_token"),
        **(params or {}),
    }
    if not query.get("bk_token"):
        query["bk_username"] = CALLER_USERNAME
    try:
        response = requests.get(_esb_url(config, path), params=query, timeout=TIMEOUT)
        data = _parse_json_response(response)
    except requests.Timeout as error:
        _warn_transport_failure(error, "Timeout")
        return None, CapabilityExecutionResult.failed_result(
            "BlueKing request timed out",
            code="provider.timeout",
            retryable=True,
        )
    except ValueError as error:
        return None, CapabilityExecutionResult.failed_result(
            str(error) or "BlueKing response is invalid",
            code="provider.invalid_response",
        )
    except requests.RequestException as error:
        _warn_transport_failure(error, "request_failed")
        return None, CapabilityExecutionResult.failed_result(
            "BlueKing request failed",
            code="provider.request_failed",
            retryable=True,
        )
    if response.status_code != 200 or not data.get("result"):
        return None, CapabilityExecutionResult.failed_result(
            "BlueKing request was rejected",
            code="provider.auth_failed",
        )
    return data, None


def _parse_page_count(count):
    if count is None:
        return None, None
    if type(count) is int:
        return count, None
    if isinstance(count, str) and count.strip().isdigit():
        return int(count.strip()), None
    return None, CapabilityExecutionResult.failed_result(
        "BlueKing directory count is invalid",
        code="provider.invalid_response",
        field="count",
    )


def _iter_esb_pages(config, path, extra_params=None):
    aggregated = []
    for page in range(1, MAX_PAGES + 1):
        params = {"page": page, "page_size": PAGE_SIZE, **(extra_params or {})}
        payload, error = _esb_get(config, path, params)
        if error:
            return None, error
        body = payload.get("data") or {}
        results = body.get("results") or []
        count, error = _parse_page_count(body.get("count"))
        if error:
            return None, error
        aggregated.extend(results)
        if not results:
            break
        if count is not None and len(aggregated) >= count:
            break
        if count is None and len(results) < PAGE_SIZE:
            break
    else:
        return None, CapabilityExecutionResult.failed_result(
            "BlueKing directory pagination exceeded the page limit",
            code="provider.invalid_response",
            field="page",
        )
    return aggregated, None


def retrieve_user_profile(config, username):
    """按用户名读取目录资料。失败不记日志，把异常交回登录绑定。"""
    error = _validate_credentials(config)
    if error or not str(username or "").strip():
        return None, "invalid_config", None
    query = {
        "bk_app_code": config.get("app_id"),
        "bk_app_secret": config.get("app_token"),
        "bk_username": CALLER_USERNAME,
        "id": username,
        "fields": "username,display_name,email,telephone",
    }
    try:
        response = requests.get(_esb_url(config, RETRIEVE_USER_PATH), params=query, timeout=TIMEOUT)
        data = _parse_json_response(response)
    except requests.Timeout as error:
        return None, "Timeout", error
    except ValueError as error:
        return None, "invalid_response", error
    except requests.RequestException as error:
        return None, "request_failed", error
    if response.status_code != 200 or not data.get("result") or not isinstance(data.get("data"), dict):
        return None, "auth_rejected", None
    user = data["data"]
    return (
        {
            "name": str(user.get("display_name") or "").strip(),
            "email": str(user.get("email") or ""),
            "mobile": str(user.get("telephone") or user.get("mobile") or ""),
        },
        None,
        None,
    )


def get_login_username(config, bk_token):
    payload, error = _esb_get(config, LOGIN_GET_USER_PATH, {"bk_token": bk_token})
    if error:
        return None, error
    user = payload.get("data") or {}
    username = str(user.get("username") or user.get("bk_username") or "").strip()
    if not username:
        return None, CapabilityExecutionResult.failed_result(
            "BlueKing user identity is missing",
            code="provider.auth_failed",
        )
    return username, None


def list_all_departments(config):
    return _iter_esb_pages(config, LIST_DEPARTMENTS_PATH)


def list_all_users(config):
    return _iter_esb_pages(config, LIST_USERS_PATH, {"fields": USER_FIELDS})


def test_esb_connection(config):
    error = _validate_credentials(config)
    if error:
        return error
    _, error = _esb_get(config, LIST_DEPARTMENTS_PATH, {"page": 1, "page_size": 1})
    return error or CapabilityExecutionResult.success_result("BlueKing base connection is ready")


def all_department_label(locale=None):
    locale_key = normalize_locale(locale)
    for name in (f"{locale_key}.yaml", "en.yaml"):
        path = _LANGUAGE_DIR / name
        if not path.is_file():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        label = raw.get("all_departments")
        if isinstance(label, str) and label.strip():
            return label.strip()
    return "All"


def department_tree(departments):
    nodes = {}
    children = {}
    for department in departments or []:
        department_id = str(department.get("id") if department.get("id") is not None else "")
        if not department_id:
            continue
        parent = department.get("parent")
        parent_id = "" if parent is None else str(parent)
        nodes[department_id] = {
            "id": department_id,
            "name": department.get("name") or department_id,
            "parent_id": parent_id,
            "children": [],
            "selectable": True,
        }

    for node in nodes.values():
        parent_id = node["parent_id"]
        if parent_id not in nodes:
            node["parent_id"] = None
        else:
            children.setdefault(parent_id, []).append(node)

    def build(parent_id):
        return [{**node, "children": build(node["id"])} for node in children.get(parent_id, [])]

    return [{**node, "children": build(node["id"])} for node in nodes.values() if node["parent_id"] is None]


def scoped_departments(departments, root_id, include_child):
    by_id = {}
    children = {}
    for item in departments or []:
        item_id = str(item.get("id") if item.get("id") is not None else "")
        if not item_id:
            continue
        by_id[item_id] = item
        parent = item.get("parent")
        parent_id = "" if parent is None else str(parent)
        children.setdefault(parent_id, []).append(item_id)
    if root_id not in by_id:
        return None
    if not include_child:
        return [by_id[root_id]]
    scoped = []
    stack = [root_id]
    seen = set()
    while stack:
        current = stack.pop()
        if current in seen or current not in by_id:
            continue
        seen.add(current)
        scoped.append(by_id[current])
        stack.extend(children.get(current, []))
    return scoped


def group_list_from_departments(departments, attach_missing_parent_to=None):
    groups = []
    for item in departments or []:
        if item.get("id") is None:
            continue
        parent = item.get("parent")
        groups.append(
            {
                "id": str(item["id"]),
                "parent_id": "" if parent is None else str(parent),
                "name": item.get("name") or "",
            }
        )
    if not attach_missing_parent_to:
        return groups
    present_ids = {group["id"] for group in groups}
    for group in groups:
        if group["parent_id"] not in present_ids:
            group["parent_id"] = attach_missing_parent_to
    return groups


def user_department_ids(user):
    ids = []
    for item in user.get("departments") or user.get("department_ids") or []:
        if isinstance(item, dict):
            department_id = item.get("id")
        else:
            department_id = item
        if department_id is None or department_id == "":
            continue
        ids.append(str(department_id))
    return ids


def normalize_users(users, selected_department_ids=None):
    selected = set(selected_department_ids or [])
    normalized = []
    for raw in users or []:
        username = str(raw.get("username") or "").strip()
        if not username:
            continue
        department_ids = user_department_ids(raw)
        if selected and not selected.intersection(department_ids):
            continue
        normalized.append(
            {
                "username": username,
                "display_name": str(raw.get("display_name") or username),
                "email": str(raw.get("email") or ""),
                "mobile": str(raw.get("telephone") or raw.get("mobile") or ""),
                "department_ids": department_ids,
            }
        )
    return normalized
