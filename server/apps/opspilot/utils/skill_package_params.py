"""智能体 × 技能包执行期参数：校验、掩码、加解密、运行时解密。

与 ``prompt_utils.skill_params`` 分离：本模块的值只进入技能包执行环境，
不替换提示词占位符。
"""

from __future__ import annotations

import copy
import re
from typing import Any

from apps.core.logger import opspilot_logger as logger
from apps.core.mixinx import EncryptMixin
from apps.opspilot.utils.prompt_utils import MASK_VALUE

PARAM_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_VARS_PER_PACKAGE = 50
MAX_VALUE_LENGTH = 64 * 1024
ALLOWED_TYPES = frozenset({"text", "password", "textarea"})


def mask_package_params(raw: Any) -> dict[str, list[dict[str, Any]]]:
    """读路径：password 项的 value 换成掩码，不修改入参。"""
    if not isinstance(raw, dict):
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    for pkg_id, items in raw.items():
        masked: list[dict[str, Any]] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            if row.get("type") == "password" and row.get("value"):
                row["value"] = MASK_VALUE
            masked.append(row)
        result[str(pkg_id)] = masked
    return result


def merge_package_params(incoming: Any, stored: Any) -> dict[str, list[dict[str, Any]]]:
    """写路径：掩码回填密文，新明文加密。incoming 为 None 时保留 stored。"""
    if incoming is None:
        return copy.deepcopy(stored) if isinstance(stored, dict) else {}
    if not isinstance(incoming, dict):
        return {}

    stored_map = stored if isinstance(stored, dict) else {}
    result: dict[str, list[dict[str, Any]]] = {}
    for pkg_id, items in incoming.items():
        stored_items = {
            str(item.get("key") or ""): item
            for item in (stored_map.get(pkg_id) or stored_map.get(str(pkg_id)) or [])
            if isinstance(item, dict) and item.get("key")
        }
        merged_items: list[dict[str, Any]] = []
        for item in copy.deepcopy(items or []):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "password":
                if item.get("value") == MASK_VALUE:
                    old = stored_items.get(str(item.get("key") or ""))
                    if old:
                        item["value"] = old.get("value", "")
                elif item.get("value"):
                    EncryptMixin.encrypt_field("value", item)
            merged_items.append(item)
        result[str(pkg_id)] = merged_items
    return result


def validate_package_params(raw: Any) -> dict[str, list[dict[str, Any]]]:
    """校验结构、变量名、重名、数量与长度。非法时抛 ValueError。"""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("技能包参数必须是对象")

    validated: dict[str, list[dict[str, Any]]] = {}
    for pkg_id, items in raw.items():
        package_id = str(pkg_id or "").strip()
        if not package_id:
            raise ValueError("技能包参数缺少 package_id")
        if not isinstance(items, list):
            raise ValueError(f"技能包 {package_id} 的参数必须是列表")
        if len(items) > MAX_VARS_PER_PACKAGE:
            raise ValueError(f"技能包 {package_id} 的变量数不能超过 {MAX_VARS_PER_PACKAGE}")

        seen: set[str] = set()
        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"技能包 {package_id} 含有非法变量项")
            key = str(item.get("key") or "").strip()
            if not key:
                raise ValueError(f"技能包 {package_id} 存在空变量名")
            if not PARAM_KEY_RE.match(key):
                raise ValueError(f"变量名不合法: {key}")
            if key in seen:
                raise ValueError(f"技能包 {package_id} 存在重复变量名: {key}")
            seen.add(key)

            value_type = item.get("type") or "text"
            if value_type not in ALLOWED_TYPES:
                raise ValueError(f"变量 {key} 的类型不合法")
            if value_type == "text" and item.get("multiline"):
                value_type = "textarea"
            value = item.get("value")
            if value is None:
                value = ""
            if not isinstance(value, str):
                value = str(value)
            if len(value) > MAX_VALUE_LENGTH:
                raise ValueError(f"变量 {key} 的值超过 {MAX_VALUE_LENGTH} 字节限制")

            normalized.append(
                {
                    "key": key,
                    "value": value,
                    "type": value_type,
                    "multiline": value_type == "textarea",
                }
            )
        validated[package_id] = normalized
    return validated


def decrypt_package_params(raw: Any) -> tuple[dict[str, dict[str, str]], dict[str, set[str]]]:
    """把存储形态解密为 ``{package_id: {key: plaintext}}`` 与加密变量名集合。"""
    params_by_pkg: dict[str, dict[str, str]] = {}
    secrets_by_pkg: dict[str, set[str]] = {}
    if not isinstance(raw, dict):
        return params_by_pkg, secrets_by_pkg
    for pkg_id, items in raw.items():
        env: dict[str, str] = {}
        secrets: set[str] = set()
        for item in items or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            row = dict(item)
            if row.get("type") == "password":
                EncryptMixin.decrypt_field("value", row)
                secrets.add(key)
            env[key] = str(row.get("value") or "")
        params_by_pkg[str(pkg_id)] = env
        secrets_by_pkg[str(pkg_id)] = secrets
    return params_by_pkg, secrets_by_pkg


def resolve_package_params(skill_id: Any, overlay: Any = None) -> tuple[dict[str, dict[str, str]], dict[str, set[str]]]:
    """运行时解密。优先使用加密 overlay（测试未保存值），否则按 skill_id 查库。"""
    raw = overlay
    if (raw is None or raw == {}) and skill_id is not None:
        raw = _load_stored_params(skill_id)
    return decrypt_package_params(raw)


def _load_stored_params(skill_id: Any) -> dict[str, list[dict[str, Any]]] | None:
    try:
        from apps.opspilot.models import LLMSkill
        from apps.opspilot.utils.db_cleanup import run_with_db_cleanup

        def _load():
            obj = LLMSkill.objects.filter(id=skill_id).only("skill_package_params").first()
            return getattr(obj, "skill_package_params", None) if obj else None

        return run_with_db_cleanup(_load)
    except Exception as exc:
        logger.debug("技能包参数查询失败: %r", exc)
        return None


def list_missing_required_params(package: dict[str, Any], configured_items: Any) -> list[str]:
    """根据技能包 variables 声明，列出未填写的必填变量名。"""
    filled: set[str] = set()
    for item in configured_items or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if key and str(item.get("value") or "").strip():
            filled.add(key)

    missing: list[str] = []
    for decl in package.get("variables") or []:
        if not isinstance(decl, dict):
            continue
        name = str(decl.get("name") or "").strip()
        if not name:
            continue
        if decl.get("required") in (True, "true", "True", 1, "1") and name not in filled:
            missing.append(name)
    return missing


def annotate_packages_missing_params(packages: Any, package_params: Any) -> list[dict[str, Any]]:
    """给 hydrate 后的技能包 snapshot 写入 missing_params（只含变量名）。"""
    params = package_params if isinstance(package_params, dict) else {}
    annotated: list[dict[str, Any]] = []
    for package in packages or []:
        if not isinstance(package, dict):
            continue
        snapshot = dict(package)
        pkg_id = str(snapshot.get("package_id") or "")
        configured = params.get(pkg_id) or params.get(snapshot.get("package_id")) or []
        snapshot["missing_params"] = list_missing_required_params(snapshot, configured)
        annotated.append(snapshot)
    return annotated


def map_params_to_skill_dirs(
    packages: Any,
    params_by_package_id: dict[str, dict[str, str]],
    secrets_by_package_id: dict[str, set[str]],
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """把 package_id 键映射成沙箱目录名（sanitize_skill_name 结果）。"""
    from apps.opspilot.services.skill_package.materializer import sanitize_skill_name

    by_dir: dict[str, dict[str, str]] = {}
    secret_values: list[str] = []
    for package in packages or []:
        if not isinstance(package, dict):
            continue
        pkg_id = str(package.get("package_id") or "")
        dir_name = sanitize_skill_name(package.get("package_id") or package.get("name"))
        env = dict(params_by_package_id.get(pkg_id) or {})
        by_dir[dir_name] = env
        for key in secrets_by_package_id.get(pkg_id) or set():
            value = env.get(key)
            if value:
                secret_values.append(value)
    return by_dir, secret_values


def format_skillenv(params: dict[str, str]) -> str:
    """把键值写成 KEY=VALUE 逐行文本，换行与引号做转义。"""
    lines: list[str] = []
    for key, value in params.items():
        escaped = str(value).replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
        if any(char in escaped for char in ' \t"#'):
            escaped = '"' + escaped.replace('"', '\\"') + '"'
        lines.append(f"{key}={escaped}")
    return "\n".join(lines) + ("\n" if lines else "")
