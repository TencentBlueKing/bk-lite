"""按组织观测实际上游出现过的监控源 ID，供规则勾选与列表筛选。"""

from django.core.cache import cache

from apps.core.logger import alert_logger as logger

_default_catalog = None


class MemoryCatalogStore:
    def __init__(self):
        self._zsets = {}
        self._values = {}

    def zadd(self, key, mapping):
        members = self._zsets.setdefault(key, {})
        members.update(mapping)
        return len(mapping)

    def zrevrange(self, key, start, end, withscores=False):
        items = sorted(self._zsets.get(key, {}).items(), key=lambda item: (-item[1], item[0]))
        count = len(items)
        if start < 0:
            start = max(count + start, 0)
        if end < 0:
            end = count + end
        sliced = items[start : end + 1] if start <= end else []
        if withscores:
            return sliced
        return [member for member, _ in sliced]

    def zcard(self, key):
        return len(self._zsets.get(key, {}))

    def zscore(self, key, member):
        return self._zsets.get(key, {}).get(member)

    def get(self, key):
        return self._values.get(key)

    def set(self, key, value, timeout=None):
        self._values[key] = value

    def add(self, key, value, timeout=None):
        if key in self._values:
            return False
        self._values[key] = value
        return True


class RedisCatalogStore:
    def __init__(self, redis):
        self._redis = redis

    def zadd(self, key, mapping):
        return self._redis.zadd(key, mapping)

    def zrevrange(self, key, start, end, withscores=False):
        rows = self._redis.zrevrange(key, start, end, withscores=withscores)
        if not withscores:
            return [_decode_member(member) for member in rows]
        return [(_decode_member(member), score) for member, score in rows]

    def zcard(self, key):
        return self._redis.zcard(key)

    def zscore(self, key, member):
        return self._redis.zscore(key, member)

    def get(self, key):
        return _decode_stored_value(self._redis.get(key))

    def set(self, key, value, timeout=None):
        if timeout is None:
            return self._redis.set(key, value)
        return self._redis.setex(key, timeout, value)

    def add(self, key, value, timeout=None):
        return bool(self._redis.set(key, value, nx=True, ex=timeout))


class DjangoCacheCatalogStore:
    def __init__(self, backend=None):
        self._cache = backend if backend is not None else cache

    def zadd(self, key, mapping):
        members = dict(self._cache.get(key) or {})
        members.update(mapping)
        self._cache.set(key, members, timeout=None)
        return len(mapping)

    def zrevrange(self, key, start, end, withscores=False):
        items = sorted((self._cache.get(key) or {}).items(), key=lambda item: (-item[1], item[0]))
        count = len(items)
        if start < 0:
            start = max(count + start, 0)
        if end < 0:
            end = count + end
        sliced = items[start : end + 1] if start <= end else []
        if withscores:
            return sliced
        return [member for member, _ in sliced]

    def zcard(self, key):
        return len(self._cache.get(key) or {})

    def zscore(self, key, member):
        return (self._cache.get(key) or {}).get(member)

    def get(self, key):
        return self._cache.get(key)

    def set(self, key, value, timeout=None):
        return self._cache.set(key, value, timeout=timeout)

    def add(self, key, value, timeout=None):
        return self._cache.add(key, value, timeout=timeout)


class PushSourceCatalog:
    KEY = "alerts:push_source_ids:v1:{team_id}"
    READY_KEY = "alerts:push_source_ids:ready:v1:{team_id}"
    MAX_MEMBERS = 2000
    STALE_SECONDS = 90 * 24 * 3600

    def __init__(self, store=None, now=None, min_interval=60):
        self.store = store if store is not None else _build_default_store()
        self._now = now if now is not None else _unix_now
        self.min_interval = min_interval
        self._throttle = {}

    def observe(self, team_ids, source_ids):
        teams = _normalize_team_ids(team_ids)
        sources = _normalize_source_ids(source_ids)
        if not teams:
            return
        now = self._now()
        for team_id in teams:
            try:
                self._observe_team(team_id, sources, now)
            except Exception as exc:
                logger.warning(
                    "push source catalog observe failed: team_id=%s error_type=%s",
                    team_id,
                    type(exc).__name__,
                )

    def list_for_teams(self, team_ids):
        now = self._now()
        cutoff = now - self.STALE_SECONDS
        best = {}
        for team_id in _normalize_team_ids(team_ids):
            rows = self.store.zrevrange(self.KEY.format(team_id=team_id), 0, -1, withscores=True) or []
            for member, score in rows:
                if score < cutoff:
                    continue
                current = best.get(member)
                if current is None or score > current:
                    best[member] = score
        return [member for member, _ in sorted(best.items(), key=lambda item: (-item[1], item[0]))]

    def _observe_team(self, team_id, source_ids, now):
        pending = []
        for source_id in source_ids:
            last = self._throttle.get((team_id, source_id))
            if last is not None and now - last < self.min_interval:
                continue
            pending.append(source_id)
        if not pending:
            return
        key = self.KEY.format(team_id=team_id)
        size = self.store.zcard(key) or 0
        mapping = {}
        rejected = 0
        if size + len(pending) <= self.MAX_MEMBERS:
            mapping = {source_id: now for source_id in pending}
        else:
            room = max(self.MAX_MEMBERS - size, 0)
            new_count = 0
            for source_id in pending:
                if self.store.zscore(key, source_id) is not None:
                    mapping[source_id] = now
                    continue
                if new_count < room:
                    mapping[source_id] = now
                    new_count += 1
                else:
                    rejected += 1
        if mapping:
            self.store.zadd(key, mapping)
        if rejected:
            logger.info(
                "push source catalog cap reached: team_id=%s size=%s rejected=%s",
                team_id,
                size,
                rejected,
            )
        self._record_throttle(team_id, mapping, now)

    def _record_throttle(self, team_id, mapping, now):
        stale_before = now - self.min_interval
        self._throttle = {key: seen for key, seen in self._throttle.items() if seen >= stale_before}
        for source_id in mapping:
            self._throttle[(team_id, source_id)] = now


def default_catalog():
    global _default_catalog
    if _default_catalog is None:
        _default_catalog = PushSourceCatalog()
    return _default_catalog


def _unix_now():
    from time import time

    return time()


def _build_default_store():
    try:
        client = cache._cache.get_client(None, write=True)
    except Exception:
        return DjangoCacheCatalogStore()
    if client is None:
        return DjangoCacheCatalogStore()
    return RedisCatalogStore(client)


def _normalize_team_ids(team_ids):
    result = []
    seen = set()
    for raw in team_ids or []:
        try:
            team_id = int(raw)
        except (TypeError, ValueError):
            continue
        if team_id in seen:
            continue
        seen.add(team_id)
        result.append(team_id)
    return result


def _normalize_source_ids(source_ids):
    result = []
    seen = set()
    for raw in source_ids or []:
        if raw is None:
            continue
        text = raw.strip() if isinstance(raw, str) else str(raw).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _decode_member(member):
    if isinstance(member, bytes):
        return member.decode()
    return member


def _decode_stored_value(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode()
    if isinstance(value, str):
        try:
            number = int(value)
        except ValueError:
            return value
        if str(number) == value:
            return number
    return value
