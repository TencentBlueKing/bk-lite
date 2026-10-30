import uuid

from django.core.cache import cache

# 槽位只表示「这条收敛已经在队列里或正在执行」。
# 任务结束就释放，记录仍是 running 时，下一次心跳还可以再投一条。
# TTL 覆盖 worker 在 finally 之前退出的情况，避免槽位永久占住。
CONVERGE_SLOT_TTL_SECONDS = 300


def action_slot_key(node_id: str) -> str:
    return f"node_converge_action_pending_{node_id}"


def install_slot_key(node_id: str) -> str:
    return f"node_converge_install_pending_{node_id}"


def new_claim_token() -> str:
    return uuid.uuid4().hex


def claim_converge_slot(cache_key: str, token: str, ttl: int = CONVERGE_SLOT_TTL_SECONDS) -> bool:
    if not token:
        return False
    return bool(cache.add(cache_key, token, timeout=ttl))


def release_converge_slot(cache_key: str, token: str | None) -> None:
    if not token:
        return
    # 只释放自己占的槽。过期后被下一次心跳换成新 token 时，不能把新槽删掉。
    if cache.get(cache_key) != token:
        return
    cache.delete(cache_key)
