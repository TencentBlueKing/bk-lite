import hashlib
import json
import logging
from typing import Dict, List, Optional

from django.core.cache import cache

from apps.alerts.enrichment.keys import resolve_binding, build_binding_key
from apps.alerts.enrichment.matcher import event_matches
from apps.alerts.enrichment.projection import project
from apps.alerts.enrichment.providers.base import get_provider

logger = logging.getLogger(__name__)

MAX_KEYS_PER_BATCH = 500
CACHE_TTL_SECONDS = 60
# 负缓存哨兵：用字符串而非 dict，避免可变默认值和 == 比较歧义
_MISS = "__enrich_miss__"


class EnrichmentEngine:
    def __init__(self, rules: Optional[List] = None):
        self._rules = rules

    def _active_rules(self):
        if self._rules is not None:
            return self._rules
        from apps.alerts.models.enrichment import EnrichmentRule
        return list(EnrichmentRule.objects.filter(is_active=True))

    @staticmethod
    def _cache_key(provider_type, provider_config, binding_key) -> str:
        """构造确定性缓存键，纳入 provider_config 避免不同配置碰撞。"""
        raw = json.dumps(
            {"pt": provider_type, "cfg": provider_config, "key": list(binding_key)},
            sort_keys=True,
            ensure_ascii=False,
        )
        digest = hashlib.md5(raw.encode("utf-8")).hexdigest()
        return "enrich:" + digest

    def enrich_batch(self, events: List[Dict]) -> None:
        try:
            rules = self._active_rules()
        except Exception:
            logger.error("[Enrichment] 加载丰富规则失败", exc_info=True)
            return
        for rule in rules:
            try:
                self._apply_rule(rule, events)
            except Exception:
                logger.error("[Enrichment] 规则执行失败 rule=%s", getattr(rule, "name", "?"), exc_info=True)

    def _apply_rule(self, rule, events: List[Dict]) -> None:
        rule_team = {int(team_id) for team_id in (getattr(rule, "team", None) or [])}
        events_by_scope: Dict[tuple, List[Dict]] = {}
        for event in events:
            event_team = {int(team_id) for team_id in (event.get("team") or [])}
            if not event_team:
                logger.warning("[Enrichment] 事件缺少组织上下文，跳过丰富")
                continue
            effective_team = event_team & rule_team if rule_team else event_team
            if not effective_team:
                continue
            events_by_scope.setdefault(tuple(sorted(effective_team)), []).append(event)

        for effective_team, scoped_events in events_by_scope.items():
            self._apply_rule_for_scope(rule, scoped_events, list(effective_team))

    def _apply_rule_for_scope(self, rule, events: List[Dict], effective_team: List[int]) -> None:
        namespace = rule.resolved_namespace
        provider_type = rule.provider_type

        # 1. 匹配 + 绑定 + 批内去重
        key_to_events: Dict = {}
        for event in events:
            if not event_matches(event, rule.match_rules):
                continue
            params = resolve_binding(event, rule.input_binding)
            if params is None:
                continue
            bkey = build_binding_key(params)
            key_to_events.setdefault(bkey, []).append(event)

        if not key_to_events:
            return

        all_keys = list(key_to_events.keys())
        if len(all_keys) > MAX_KEYS_PER_BATCH:
            logger.warning("[Enrichment] 单批丰富 key 数 %s 超上限 %s，截断", len(all_keys), MAX_KEYS_PER_BATCH)
            all_keys = all_keys[:MAX_KEYS_PER_BATCH]

        # 2. 查缓存（含负结果）
        provider_config = dict(rule.provider_config or {})
        provider_config["_authorized_team_ids"] = effective_team
        records_by_key: Dict = {}
        miss_keys = []
        for bkey in all_keys:
            cached = cache.get(self._cache_key(provider_type, provider_config, bkey))
            if cached == _MISS:
                records_by_key[bkey] = []
            elif cached is not None:
                records_by_key[bkey] = cached
            else:
                miss_keys.append(bkey)

        # 3. 未命中走 provider 批量查询 + 回填缓存
        if miss_keys:
            provider = get_provider(provider_type)
            try:
                fetched = provider.fetch_batch(miss_keys, provider_config)
            except Exception:
                logger.error("[Enrichment] Provider 查询失败 provider_type=%s", provider_type, exc_info=True)
                fetched = {}
            for bkey in miss_keys:
                recs = fetched.get(bkey) or []
                records_by_key[bkey] = recs
                cache.set(self._cache_key(provider_type, provider_config, bkey), recs or _MISS, CACHE_TTL_SECONDS)

        # 4. 投影写回
        for bkey in all_keys:
            projected = project(records_by_key.get(bkey, []), rule.output_projection, rule.on_multiple)
            if not projected:
                continue
            for event in key_to_events[bkey]:
                event.setdefault("enrichment", {})[namespace] = projected
