"""按组织、集成源缓存监控源事件数量，供集成源详情展示。"""

from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count
from django.utils import timezone

from apps.alerts.models.models import Event
from apps.core.logger import alert_logger as logger
from apps.core.utils.viewset_utils import build_json_membership_query

_default_counts = None


class MemoryHashStore:
    def __init__(self):
        self._hashes = {}
        self._values = {}

    def hincrby(self, key, field, amount):
        bucket = self._hashes.setdefault(key, {})
        bucket[field] = int(bucket.get(field, 0)) + int(amount)
        return bucket[field]

    def hgetall(self, key):
        return dict(self._hashes.get(key, {}))

    def hlen(self, key):
        return len(self._hashes.get(key, {}))

    def hexists(self, key, field):
        return field in self._hashes.get(key, {})

    def hset(self, key, mapping):
        bucket = self._hashes.setdefault(key, {})
        bucket.update({field: int(value) for field, value in mapping.items()})
        return len(mapping)

    def get(self, key):
        return self._values.get(key)

    def set(self, key, value, timeout=None):
        self._values[key] = value

    def add(self, key, value, timeout=None):
        if key in self._values:
            return False
        self._values[key] = value
        return True

    def delete(self, key):
        self._values.pop(key, None)
        self._hashes.pop(key, None)


class RedisHashStore:
    def __init__(self, redis):
        self._redis = redis

    def hincrby(self, key, field, amount):
        return self._redis.hincrby(key, field, amount)

    def hgetall(self, key):
        rows = self._redis.hgetall(key) or {}
        return {_decode_member(field): _as_count(value) for field, value in rows.items()}

    def hlen(self, key):
        return self._redis.hlen(key) or 0

    def hexists(self, key, field):
        return bool(self._redis.hexists(key, field))

    def hset(self, key, mapping):
        if not mapping:
            return 0
        return self._redis.hset(key, mapping=mapping)

    def get(self, key):
        return _decode_stored_value(self._redis.get(key))

    def set(self, key, value, timeout=None):
        if timeout is None:
            return self._redis.set(key, value)
        return self._redis.setex(key, timeout, value)

    def add(self, key, value, timeout=None):
        return bool(self._redis.set(key, value, nx=True, ex=timeout))

    def delete(self, key):
        return self._redis.delete(key)


class DjangoCacheHashStore:
    def __init__(self, backend=None):
        self._cache = backend if backend is not None else cache

    def hincrby(self, key, field, amount):
        bucket = dict(self._cache.get(key) or {})
        bucket[field] = int(bucket.get(field, 0)) + int(amount)
        self._cache.set(key, bucket, timeout=None)
        return bucket[field]

    def hgetall(self, key):
        return dict(self._cache.get(key) or {})

    def hlen(self, key):
        return len(self._cache.get(key) or {})

    def hexists(self, key, field):
        return field in (self._cache.get(key) or {})

    def hset(self, key, mapping):
        bucket = dict(self._cache.get(key) or {})
        bucket.update({field: int(value) for field, value in mapping.items()})
        self._cache.set(key, bucket, timeout=None)
        return len(mapping)

    def get(self, key):
        return self._cache.get(key)

    def set(self, key, value, timeout=None):
        return self._cache.set(key, value, timeout=timeout)

    def add(self, key, value, timeout=None):
        return self._cache.add(key, value, timeout=timeout)

    def delete(self, key):
        self._cache.delete(key)
        return 1


class PushSourceCountCache:
    KEY = "alerts:push_source_counts:v1:{team_id}:{source_id}"
    READY_KEY = "alerts:push_source_counts:ready:v1:{team_id}:{source_id}"
    LOCK_KEY = "alerts:push_source_counts:rebuild:v1:{team_id}:{source_id}"
    MAX_MEMBERS = 2000
    STALE_SECONDS = 90 * 24 * 3600
    REBUILD_LOCK_TIMEOUT = 30

    def __init__(self, store=None):
        self.store = store if store is not None else _build_default_store()

    def hash_key(self, team_id, source_id):
        return self.KEY.format(team_id=team_id, source_id=source_id)

    def ready_key(self, team_id, source_id):
        return self.READY_KEY.format(team_id=team_id, source_id=source_id)

    def lock_key(self, team_id, source_id):
        return self.LOCK_KEY.format(team_id=team_id, source_id=source_id)

    def observe_events(self, events):
        buckets = {}
        for event in events or []:
            source_id = _integration_source_id(event)
            push_source_id = _normalize_id(getattr(event, "push_source_id", None))
            teams = _normalize_team_ids(getattr(event, "team", None))
            if not source_id or not push_source_id or not teams:
                continue
            for team_id in teams:
                key = (team_id, source_id, push_source_id)
                buckets[key] = buckets.get(key, 0) + 1
        for (team_id, source_id, push_source_id), amount in buckets.items():
            try:
                self._incr(team_id, source_id, push_source_id, amount)
            except Exception as exc:
                logger.warning(
                    "push source counts observe failed: team_id=%s source_id=%s error_type=%s",
                    team_id,
                    source_id,
                    type(exc).__name__,
                )

    def list_for_source(self, team_ids, source_id):
        source_id = _normalize_id(source_id)
        if not source_id:
            return []
        merged = {}
        for team_id in _normalize_team_ids(team_ids):
            for member, count in self._rows_for_team_source(team_id, source_id):
                merged[member] = merged.get(member, 0) + count
        return [{"id": member, "count": count} for member, count in sorted(merged.items(), key=lambda item: (-item[1], item[0]))]

    def rebuild_for_team_source(self, team_id, source_id):
        lock_key = self.lock_key(team_id, source_id)
        try:
            acquired = bool(self.store.add(lock_key, 1, timeout=self.REBUILD_LOCK_TIMEOUT))
        except Exception:
            acquired = True
        if not acquired:
            return {}
        mapping = {}
        try:
            mapping = self._event_mapping(team_id, source_id)
            if len(mapping) > self.MAX_MEMBERS:
                mapping = dict(sorted(mapping.items(), key=lambda item: (-item[1], item[0]))[: self.MAX_MEMBERS])
            key = self.hash_key(team_id, source_id)
            try:
                if mapping:
                    self.store.hset(key, mapping)
                self.store.set(self.ready_key(team_id, source_id), 1)
            except Exception:
                return mapping
            return mapping
        finally:
            try:
                self.store.delete(lock_key)
            except Exception:
                pass

    def _incr(self, team_id, source_id, push_source_id, amount):
        key = self.hash_key(team_id, source_id)
        if not self.store.hexists(key, push_source_id):
            size = self.store.hlen(key) or 0
            if size >= self.MAX_MEMBERS:
                logger.info(
                    "push source counts cap reached: team_id=%s source_id=%s size=%s rejected=%s",
                    team_id,
                    source_id,
                    size,
                    1,
                )
                return
        self.store.hincrby(key, push_source_id, amount)

    def _rows_for_team_source(self, team_id, source_id):
        key = self.hash_key(team_id, source_id)
        try:
            if self.store.get(self.ready_key(team_id, source_id)) != 1:
                mapping = self.rebuild_for_team_source(team_id, source_id) or {}
                rows = self.store.hgetall(key) or {}
                if rows:
                    return [(member, _as_count(count)) for member, count in rows.items()]
                return list(mapping.items())
            return [(member, _as_count(count)) for member, count in (self.store.hgetall(key) or {}).items()]
        except Exception:
            mapping = {}
            try:
                mapping = self.rebuild_for_team_source(team_id, source_id) or {}
            except Exception as exc:
                logger.warning(
                    "push source counts rebuild failed: team_id=%s source_id=%s error_type=%s",
                    team_id,
                    source_id,
                    type(exc).__name__,
                )
            if mapping:
                return list(mapping.items())
            try:
                return [(member, _as_count(count)) for member, count in (self.store.hgetall(key) or {}).items()]
            except Exception:
                return []

    def _event_mapping(self, team_id, source_id):
        cutoff = timezone.now() - timedelta(seconds=self.STALE_SECONDS)
        base = Event.objects.filter(source__source_id=source_id, received_at__gte=cutoff).exclude(push_source_id="")
        qs = base.filter(build_json_membership_query(base, "team", [team_id]))
        mapping = {}
        for row in qs.values("push_source_id").annotate(total=Count("id")):
            member = _normalize_id(row.get("push_source_id"))
            if not member:
                continue
            mapping[member] = int(row["total"])
        return mapping


def remember_event_counts(events):
    default_counts().observe_events(events)


def default_counts():
    global _default_counts
    if _default_counts is None:
        _default_counts = PushSourceCountCache()
    return _default_counts


def _build_default_store():
    try:
        client = cache._cache.get_client(None, write=True)
    except Exception:
        return DjangoCacheHashStore()
    if client is None:
        return DjangoCacheHashStore()
    return RedisHashStore(client)


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


def _normalize_id(value):
    if value is None:
        return ""
    text = value.strip() if isinstance(value, str) else str(value).strip()
    return text


def _integration_source_id(event):
    source = getattr(event, "source", None)
    return _normalize_id(getattr(source, "source_id", None))


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


def _as_count(value):
    decoded = _decode_stored_value(value)
    try:
        return int(decoded or 0)
    except (TypeError, ValueError):
        return 0
