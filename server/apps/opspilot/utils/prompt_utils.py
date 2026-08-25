import copy

from apps.core.logger import opspilot_logger as logger
from apps.core.mixinx import EncryptMixin

MASK_VALUE = "******"


def resolve_skill_params(skill_prompt: str, skill_params: list) -> str:
    """解密 password 类型参数，将 skill_prompt 中的 {{key}} 替换为真实值。

    Args:
        skill_prompt: 包含 {{key}} 占位符的 prompt 文本
        skill_params: 参数列表，每项包含 key, value, type

    Returns:
        替换后的 prompt 文本
    """
    if not skill_params or not skill_prompt:
        return skill_prompt or ""

    params = copy.deepcopy(skill_params)
    for param in params:
        if param.get("type") == "password":
            EncryptMixin.decrypt_field("value", param)
        key = param.get("key", "")
        value = param.get("value", "")
        if key:
            skill_prompt = skill_prompt.replace("{{" + key + "}}", str(value))
    return skill_prompt


def merge_skill_params(frontend_params: list, db_params: list) -> list:
    """合并前端传入的 skill_params 和 DB 中的 skill_params。

    前端传入的 password 类型参数如果值为 '******'，则从 DB 中取回真实加密值；
    其余情况直接使用前端传入的值（包括用户新输入的明文密码）。

    Args:
        frontend_params: 前端传入的参数列表（password 值可能为 '******' 或明文）
        db_params: DB 中存储的参数列表（password 值为加密密文）

    Returns:
        合并后的参数列表，可直接传给 resolve_skill_params
    """
    if not frontend_params:
        return db_params or []

    db_param_map = {p.get("key"): p for p in (db_params or [])}
    merged = []
    for param in copy.deepcopy(frontend_params):
        if param.get("type") == "password" and param.get("value") == MASK_VALUE:
            # 前端传来掩码值，从 DB 取回真实加密值
            db_param = db_param_map.get(param.get("key"))
            if db_param:
                param["value"] = db_param["value"]
        elif param.get("type") == "password" and param.get("value") != MASK_VALUE:
            # 用户新输入的明文密码，需要加密后再解密（resolve 时会解密）
            # 这里直接保留明文，resolve_skill_params 的 decrypt_field 对明文会跳过
            pass
        merged.append(param)
    return merged
