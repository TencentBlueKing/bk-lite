import copy
from uuid import uuid4

from apps.core.exceptions.base_app_exception import BaseAppException


class CollectCredentialPoolService:
    """负责凭据池 normalize、校验、diff 和回滚压平。"""

    MAX_POOL_SIZE = 3

    @classmethod
    def normalize_pool(cls, raw_credential):
        """将 dict | list[dict] 统一为有序凭据列表，并补齐 credential_id。"""
        if raw_credential in (None, ""):
            return []

        if isinstance(raw_credential, dict):
            raw_pool = [raw_credential]
        elif isinstance(raw_credential, list):
            raw_pool = raw_credential
        else:
            raise BaseAppException("采集凭据格式错误！")

        normalized_pool = []
        for item in raw_pool:
            if not isinstance(item, dict):
                raise BaseAppException("采集凭据格式错误！")
            normalized_item = copy.deepcopy(item)
            normalized_item.setdefault("credential_id", cls._new_credential_id())
            normalized_pool.append(normalized_item)
        return normalized_pool

    @classmethod
    def validate_pool_shape(cls, pool):
        """校验凭据池数量与字段结构。"""
        if not pool:
            raise BaseAppException("采集凭据不能为空！")
        if len(pool) > cls.MAX_POOL_SIZE:
            raise BaseAppException("采集凭据最多支持3组！")
        for item in pool:
            if not isinstance(item, dict):
                raise BaseAppException("采集凭据格式错误！")

        # 仅 SNMP：凭据自带 version 字段（SSH/数据库/云等均不含），按各自版本校验必填项，
        # 允许 v2/v2c/v3 在同一任务内混用；其他采集类型维持原"字段结构一致"约束不变。
        if all(item.get("version") for item in pool):
            for index, item in enumerate(pool):
                cls._validate_snmp_credential(item, index)
            return

        expected_keys = None
        for item in pool:
            item_keys = set(item.keys()) - {"credential_id"}
            if expected_keys is None:
                expected_keys = item_keys
                continue
            if item_keys != expected_keys:
                raise BaseAppException("同一任务的采集凭据字段必须保持一致！")

    @classmethod
    def _validate_snmp_credential(cls, cred, index):
        """按 SNMP 版本校验单条凭据必填项，规则与 agent 侧 SnmpAuth.validate 对齐。"""
        label = f"第 {index + 1} 组凭据"
        version = str(cred.get("version", "")).strip().lower()
        if version in ("v2", "v2c"):
            if not cred.get("community"):
                raise BaseAppException(f"{label}（{version}）缺少团体字！")
        elif version == "v3":
            if not cred.get("username"):
                raise BaseAppException(f"{label}（v3）缺少用户名！")
            level = str(cred.get("level", "")).strip().lower()
            if level in ("authnopriv", "authpriv") and (not cred.get("integrity") or not cred.get("authkey")):
                raise BaseAppException(f"{label}（v3/{level}）缺少认证算法或认证密钥！")
            if level == "authpriv" and (not cred.get("privacy") or not cred.get("privkey")):
                raise BaseAppException(f"{label}（v3/authPriv）缺少加密算法或加密密钥！")
        else:
            raise BaseAppException(f"{label} 的 SNMP 版本 {version or '(空)'} 不支持！")

    @staticmethod
    def diff_pool(old_pool, new_pool):
        """返回 (added_ids, removed_ids, edited_ids)，排序变化不算编辑。"""
        old_map = {
            item.get("credential_id"): {k: v for k, v in item.items() if k != "credential_id"}
            for item in old_pool
            if isinstance(item, dict) and item.get("credential_id")
        }
        new_map = {
            item.get("credential_id"): {k: v for k, v in item.items() if k != "credential_id"}
            for item in new_pool
            if isinstance(item, dict) and item.get("credential_id")
        }

        old_ids = set(old_map.keys())
        new_ids = set(new_map.keys())

        added_ids = sorted(new_ids - old_ids)
        removed_ids = sorted(old_ids - new_ids)
        edited_ids = sorted(
            credential_id
            for credential_id in (old_ids & new_ids)
            if old_map[credential_id] != new_map[credential_id]
        )
        return added_ids, removed_ids, edited_ids

    @classmethod
    def flatten_pool_to_primary(cls, raw_credential):
        """回滚前将凭据池压平成首个凭据对象。"""
        pool = cls.normalize_pool(raw_credential)
        if not pool:
            return {}
        primary = copy.deepcopy(pool[0])
        primary.pop("credential_id", None)
        return primary

    @staticmethod
    def _new_credential_id():
        return f"cred_{uuid4().hex[:12]}"