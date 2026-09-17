"""按组织观测实际上游出现过的监控源 ID，供规则勾选与列表筛选。"""

import math
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from apps.alerts.models import Alert
from apps.alerts.utils.permission_scope import apply_team_scope_with_group_ids
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

    def delete(self, key):
        self._values.pop(key, None)
        self._zsets.pop(key, None)

    def zrem(self, key, *members):
        stored = self._zsets.get(key)
        if not stored:
            return 0
        removed = 0
        for member in members:
            if member in stored:
                del stored[member]
                removed += 1
        return removed

    def zremrangebyscore(self, key, min_score, max_score):
        members = self._zsets.get(key)
        if not members:
            return 0
        lo = _as_score_bound(min_score)
        hi = _as_score_bound(max_score)
        removed = [member for member, score in members.items() if lo <= score <= hi]
        for member in removed:
            del members[member]
        return len(removed)


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

    def delete(self, key):
        return self._redis.delete(key)

    def zrem(self, key, *members):
        if not members:
            return 0
        return self._redis.zrem(key, *members)

    def zremrangebyscore(self, key, min_score, max_score):
        return self._redis.zremrangebyscore(key, min_score, max_score)


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

    def delete(self, key):
        return self._cache.delete(key)

    def zrem(self, key, *members):
        stored = dict(self._cache.get(key) or {})
        if not stored:
            return 0
        removed = 0
        for member in members:
            if member in stored:
                del stored[member]
                removed += 1
        if removed:
            self._cache.set(key, stored, timeout=None)
        return removed

    def zremrangebyscore(self, key, min_score, max_score):
        members = dict(self._cache.get(key) or {})
        if not members:
            return 0
        lo = _as_score_bound(min_score)
        hi = _as_score_bound(max_score)
        kept = {member: score for member, score in members.items() if not (lo <= score <= hi)}
        removed = len(members) - len(kept)
        if removed:
            self._cache.set(key, kept, timeout=None)
        return removed


class PushSourceCatalog:
    KEY = "alerts:push_source_ids:v1:{team_id}"
    READY_KEY = "alerts:push_source_ids:ready:v1:{team_id}"
    LOCK_KEY = "alerts:push_source_ids:rebuild:v1:{team_id}"
    MAX_MEMBERS = 2000
    STALE_SECONDS = 90 * 24 * 3600
    REBUILD_LOCK_TIMEOUT = 30

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
            for member, score in self._rows_for_team(team_id):
                if score < cutoff:
                    continue
                current = best.get(member)
                if current is None or score > current:
                    best[member] = score
        return [member for member, _ in sorted(best.items(), key=lambda item: (-item[1], item[0]))]

    def rebuild_for_team(self, team_id):
        lock_key = self.LOCK_KEY.format(team_id=team_id)
        try:
            acquired = bool(self.store.add(lock_key, 1, timeout=self.REBUILD_LOCK_TIMEOUT))
        except Exception:
            acquired = True
        if not acquired:
            return {}
        mapping = {}
        try:
            mapping = self._snapshot_mapping(team_id)
            if len(mapping) > self.MAX_MEMBERS:
                mapping = dict(sorted(mapping.items(), key=lambda item: (-item[1], item[0]))[: self.MAX_MEMBERS])
            key = self.KEY.format(team_id=team_id)
            try:
                if mapping:
                    self.store.zadd(key, mapping)
                self._trim_stale(key, self._now())
                self._keep_newest_members(key)
                self.store.set(self.READY_KEY.format(team_id=team_id), 1)
            except Exception:
                return mapping
            return mapping
        finally:
            try:
                self.store.delete(lock_key)
            except Exception:
                pass

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
        self._trim_stale(key, now)
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

    def _rows_for_team(self, team_id):
        key = self.KEY.format(team_id=team_id)
        try:
            if self.store.get(self.READY_KEY.format(team_id=team_id)) != 1:
                mapping = self.rebuild_for_team(team_id) or {}
                rows = self.store.zrevrange(key, 0, -1, withscores=True) or []
                if rows:
                    return rows
                if mapping:
                    return list(mapping.items())
                return []
            return self.store.zrevrange(key, 0, -1, withscores=True) or []
        except Exception:
            mapping = {}
            try:
                mapping = self.rebuild_for_team(team_id) or {}
            except Exception as exc:
                logger.warning(
                    "push source catalog rebuild failed: team_id=%s error_type=%s",
                    team_id,
                    type(exc).__name__,
                )
            if mapping:
                return list(mapping.items())
            try:
                return self.store.zrevrange(key, 0, -1, withscores=True) or []
            except Exception:
                return []

    def _snapshot_mapping(self, team_id):
        cutoff = timezone.now() - timedelta(seconds=self.STALE_SECONDS)
        qs = Alert.objects.filter(Q(last_event_time__gte=cutoff) | Q(last_event_time__isnull=True, updated_at__gte=cutoff))
        qs = apply_team_scope_with_group_ids(qs, [team_id])
        mapping = {}
        for alert in qs.only("push_source_ids", "last_event_time", "updated_at").iterator():
            moment = alert.last_event_time or alert.updated_at
            if moment is None:
                continue
            score = int(moment.timestamp())
            for source_id in _normalize_source_ids(alert.push_source_ids or []):
                current = mapping.get(source_id)
                if current is None or score > current:
                    mapping[source_id] = score
        return mapping

    def _trim_stale(self, key, now):
        cutoff = now - self.STALE_SECONDS
        self.store.zremrangebyscore(key, float("-inf"), math.nextafter(float(cutoff), float("-inf")))

    def _keep_newest_members(self, key):
        while (self.store.zcard(key) or 0) > self.MAX_MEMBERS:
            overflow = self.store.zrevrange(key, self.MAX_MEMBERS, -1)
            if not overflow:
                return
            self.store.zrem(key, *overflow)

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


def _as_score_bound(value):
    if value in ("-inf", b"-inf"):
        return float("-inf")
    if value in ("+inf", "inf", b"+inf", b"inf"):
        return float("inf")
    return float(value)
