"""CMDB ``list_instances`` NATS 迁移期短时签名。

Server RPC 可通过 ``CMDB_NATS_LIST_INSTANCES_SIGN_V3=true`` 把 v2 升级为签名
v3；该开关默认关闭，确保双读版本先完成滚动部署。原始 v2 默认继续兼容，可通过
``CMDB_NATS_LIST_INSTANCES_ALLOW_LEGACY_V2=false`` 在观测清零后关闭；回滚时先关闭
发送侧 v3，再临时重新打开 v2。密钥轮换沿用 Django ``SECRET_KEY_FALLBACKS``，旧
密钥至少保留一个签名最大年龄后再删除。

该签名只证明调用方持有 Server 应用密钥，不代表 NATS broker publisher 身份，也不
替代后续的主体拆分与 subject ACL 收紧。
"""

import json
import os
import threading
import time
from copy import deepcopy

from django.core import signing
from django.core.serializers.json import DjangoJSONEncoder

from apps.core.logger import cmdb_logger as logger

LIST_INSTANCES_AUDIENCE = "cmdb.list_instances"
LIST_INSTANCES_OPERATION = "list_instances"
LIST_INSTANCES_AUTH_FIELD = "_auth"
LIST_INSTANCES_SIGNING_SALT = "bk-lite.cmdb.list-instances.v3"
LIST_INSTANCES_AUTH_MAX_AGE_SECONDS = 300
LIST_INSTANCES_SIGN_V3_ENV = "CMDB_NATS_LIST_INSTANCES_SIGN_V3"
LIST_INSTANCES_LEGACY_ENV = "CMDB_NATS_LIST_INSTANCES_ALLOW_LEGACY_V2"
LIST_INSTANCES_LEGACY_OBSERVATION_INTERVAL_SECONDS = 300

_INVALID_AUTH_MESSAGE = "invalid or expired list_instances authorization"
_legacy_observation_lock = threading.Lock()
_legacy_next_observation_at = 0.0


def _legacy_v2_enabled() -> bool:
    return os.getenv(LIST_INSTANCES_LEGACY_ENV, "true").strip().lower() in {"1", "true", "yes", "on"}


def list_instances_v3_signing_enabled() -> bool:
    """仅在双读 handler 全部就绪后开启发送侧 v3。"""

    return os.getenv(LIST_INSTANCES_SIGN_V3_ENV, "false").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_transport_params(params: dict) -> dict:
    """按 NATS 的 DjangoJSONEncoder 语义规范化签名参数。"""

    return json.loads(json.dumps(params, cls=DjangoJSONEncoder))


def _observe_legacy_v2_use() -> None:
    """有界记录旧协议使用；日志不携带请求数据。"""

    global _legacy_next_observation_at

    now = time.monotonic()
    with _legacy_observation_lock:
        if now < _legacy_next_observation_at:
            return
        _legacy_next_observation_at = now + LIST_INSTANCES_LEGACY_OBSERVATION_INTERVAL_SECONDS

    logger.warning("CMDB NATS list_instances legacy v2 request accepted; migrate caller to signed v3")


def prepare_list_instances_rpc_params(params: dict) -> dict:
    """复制合法 v2 参数、升级为 v3，并绑定完整查询参数。"""

    if not isinstance(params, dict) or str(params.get("protocol_version") or "") != "2":
        raise ValueError("only list_instances protocol v2 can be upgraded")

    prepared = _normalize_transport_params(deepcopy(params))
    prepared["protocol_version"] = "3"
    claims = {
        "aud": LIST_INSTANCES_AUDIENCE,
        "op": LIST_INSTANCES_OPERATION,
        "params": deepcopy(prepared),
    }
    prepared[LIST_INSTANCES_AUTH_FIELD] = signing.dumps(
        claims,
        salt=LIST_INSTANCES_SIGNING_SALT,
        compress=True,
    )
    return prepared


def _verify_v3_params(params: dict) -> None:
    token = params.get(LIST_INSTANCES_AUTH_FIELD)
    if not isinstance(token, str) or not token:
        raise ValueError(_INVALID_AUTH_MESSAGE)

    try:
        claims = signing.loads(
            token,
            salt=LIST_INSTANCES_SIGNING_SALT,
            max_age=LIST_INSTANCES_AUTH_MAX_AGE_SECONDS,
        )
    except signing.BadSignature as exc:
        raise ValueError(_INVALID_AUTH_MESSAGE) from exc

    unsigned_params = deepcopy(params)
    unsigned_params.pop(LIST_INSTANCES_AUTH_FIELD, None)
    if not isinstance(claims, dict) or claims != {
        "aud": LIST_INSTANCES_AUDIENCE,
        "op": LIST_INSTANCES_OPERATION,
        "params": unsigned_params,
    }:
        raise ValueError(_INVALID_AUTH_MESSAGE)


def authorize_list_instances_params(params: dict) -> None:
    """授权 v2/v3 请求；v3 的任何不匹配都在查询前失败关闭。"""

    protocol_version = str((params or {}).get("protocol_version") or "") if isinstance(params, dict) else ""
    if protocol_version == "2":
        if not _legacy_v2_enabled():
            raise ValueError("legacy list_instances protocol v2 is disabled")
        _observe_legacy_v2_use()
        return
    if protocol_version == "3":
        _verify_v3_params(params)
        return
    raise ValueError("unsupported CMDB list_instances protocol version")
