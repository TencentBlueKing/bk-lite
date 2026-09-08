import hashlib
import json
import time
from datetime import datetime, timezone
from threading import BoundedSemaphore
from time import monotonic
from typing import Dict, List, Optional
from uuid import uuid4

from django.core.cache import cache

from apps.alerts.enrichment.circuit_breaker import CircuitBreaker
from apps.alerts.enrichment.keys import build_binding_key, resolve_binding
from apps.alerts.enrichment.matcher import event_matches
from apps.alerts.enrichment.merge import merge_namespace_payload
from apps.alerts.enrichment.projection import project
from apps.alerts.enrichment.providers.base import FetchBatchResult, get_provider
from apps.alerts.enrichment.result import EnrichmentBatchResult, EnrichmentSummary, RuleOutcome
from apps.alerts.enrichment.telemetry import EnrichmentTelemetry
from apps.core.logger import alert_logger as logger

MAX_KEYS_PER_PROVIDER_CALL = 500
CACHE_TTL_SECONDS = 60
DEFAULT_BATCH_BUDGET_SECONDS = 5
MAX_BATCH_BUDGET_SECONDS = 10
SINGLEFLIGHT_WAIT_SECONDS = 0.3
SINGLEFLIGHT_LEASE_SECONDS = 15
MAX_OUTCOMES = 100
MAX_EVENT_REASONS = 20
_PROVIDER_SLOTS = BoundedSemaphore(4)
_MISS = "__enrich_miss__"


def _chunks(values: List, size: int):
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


class EnrichmentEngine:
    def __init__(
        self,
        rules: Optional[List] = None,
        *,
        cache_backend=None,
        clock=monotonic,
        sleeper=time.sleep,
        batch_budget_seconds: int = DEFAULT_BATCH_BUDGET_SECONDS,
        telemetry=None,
    ):
        self._rules = rules
        self._cache = cache_backend if cache_backend is not None else cache
        self._clock = clock
        self._sleeper = sleeper
        self._batch_budget_seconds = max(1, min(int(batch_budget_seconds), MAX_BATCH_BUDGET_SECONDS))
        self._breaker = CircuitBreaker(cache_backend=self._cache, clock=clock)
        self._telemetry = telemetry if telemetry is not None else EnrichmentTelemetry(self._cache)

    def _record_cache_metric(self, provider_type: str, result: str, count: int = 1) -> None:
        try:
            self._telemetry.record_cache(provider_type, result, count)
        except Exception:
            return

    def _record_provider_metric(self, provider_type: str, status: str, duration_ms: int, count: int) -> None:
        try:
            self._telemetry.record_provider(provider_type, status, duration_ms, count)
        except Exception:
            return

    def _record_circuit_transition(self, provider_type: str, to_state: str | None) -> None:
        if not to_state:
            return
        try:
            self._telemetry.record_circuit_transition(provider_type, to_state)
        except Exception:
            return

    def _active_rules(self):
        if self._rules is not None:
            return self._rules
        from apps.alerts.models.enrichment import EnrichmentRule

        return list(EnrichmentRule.objects.filter(is_active=True).order_by("id"))

    @staticmethod
    def _cache_key(provider_type, provider_config, binding_key) -> str:
        raw = json.dumps(
            {"pt": provider_type, "cfg": provider_config, "key": list(binding_key)},
            sort_keys=True,
            ensure_ascii=False,
        )
        digest = hashlib.md5(raw.encode("utf-8")).hexdigest()
        return "enrich:" + digest

    @staticmethod
    def _circuit_key(provider_type, provider_config) -> str:
        raw = json.dumps(
            {"pt": provider_type, "cfg": provider_config},
            sort_keys=True,
            ensure_ascii=False,
        )
        return "enrich:circuit:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _singleflight_key(cache_key: str) -> str:
        return f"{cache_key}:flight"

    @staticmethod
    def _append_outcome(outcomes: List[RuleOutcome], rule, namespace: str, status: str, count: int) -> None:
        if count and len(outcomes) < MAX_OUTCOMES:
            outcomes.append(
                RuleOutcome(
                    rule_id=getattr(rule, "id", None),
                    namespace=namespace,
                    status=status,
                    count=count,
                )
            )

    @staticmethod
    def _record_event_status(event: Dict, rule, namespace: str, status: str) -> None:
        meta = event.setdefault(
            "enrichment_meta",
            {"schema_version": 1, "status": "skipped", "reasons": []},
        )
        reasons = meta.setdefault("reasons", [])
        reason = {
            "rule_id": getattr(rule, "id", None),
            "namespace": namespace,
            "status": status,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        identity = (reason["rule_id"], namespace, status)
        if len(reasons) < MAX_EVENT_REASONS and all((item.get("rule_id"), item.get("namespace"), item.get("status")) != identity for item in reasons):
            reasons.append(reason)

    @staticmethod
    def _finalize_event_meta(events: List[Dict]) -> None:
        failure_codes = {
            "provider_failed",
            "circuit_open",
            "budget_exhausted",
            "provider_saturated",
        }
        for event in events:
            meta = event.setdefault(
                "enrichment_meta",
                {"schema_version": 1, "status": "skipped", "reasons": []},
            )
            statuses = {item.get("status") for item in meta.get("reasons", [])}
            has_data = bool(event.get("enrichment"))
            has_failure = bool(statuses & failure_codes) or ("inflight_coalesced" in statuses and not has_data)
            if has_data and has_failure:
                meta["status"] = "partial"
            elif has_data:
                meta["status"] = "success"
            elif has_failure:
                meta["status"] = "failed"
            else:
                meta["status"] = "skipped"

    def enrich_batch(self, events: List[Dict]) -> EnrichmentBatchResult:
        started_at = self._clock()
        deadline = started_at + self._batch_budget_seconds
        summary = EnrichmentSummary(received=len(events))
        outcomes: List[RuleOutcome] = []
        writers: Dict[tuple, List[int]] = {}
        try:
            rules = self._active_rules()
        except Exception:
            logger.error("[Enrichment] 加载丰富规则失败", exc_info=True)
            summary.failed = len(events)
            return self._finish(events, summary, outcomes, started_at)

        for rule in rules:
            if self._clock() >= deadline:
                summary.budget_exhausted += len(events)
                summary.failed += len(events)
                for event in events:
                    self._record_event_status(
                        event,
                        rule,
                        getattr(rule, "resolved_namespace", ""),
                        "budget_exhausted",
                    )
                self._append_outcome(outcomes, rule, getattr(rule, "resolved_namespace", ""), "budget_exhausted", len(events))
                break
            try:
                self._apply_rule(rule, events, summary, outcomes, writers, deadline)
            except Exception:
                logger.error("[Enrichment] 规则执行失败 rule=%s", getattr(rule, "name", "?"), exc_info=True)
                summary.failed += 1
                self._append_outcome(outcomes, rule, getattr(rule, "resolved_namespace", ""), "provider_failed", 1)

        summary.enriched = sum(bool(event.get("enrichment")) for event in events)
        return self._finish(events, summary, outcomes, started_at)

    def _finish(self, events, summary, outcomes, started_at):
        self._finalize_event_meta(events)
        summary.duration_ms = max(0, int((self._clock() - started_at) * 1000))
        result = EnrichmentBatchResult(events=events, summary=summary, outcomes=outcomes)
        if self._telemetry is not None:
            try:
                self._telemetry.record(summary)
            except Exception as exc:
                logger.debug("[Enrichment] 运行指标记录失败 error_type=%s", type(exc).__name__)
        return result

    def _apply_rule(self, rule, events, summary, outcomes, writers, deadline) -> None:
        rule_team = {int(team_id) for team_id in (getattr(rule, "team", None) or [])}
        events_by_scope: Dict[tuple, List[Dict]] = {}
        missing_team = 0
        team_mismatch = 0
        for event in events:
            event_team = {int(team_id) for team_id in (event.get("team") or [])}
            if not event_team:
                missing_team += 1
                self._record_event_status(event, rule, getattr(rule, "resolved_namespace", ""), "team_mismatch")
                logger.warning("[Enrichment] 事件缺少组织上下文，跳过丰富")
                continue
            effective_team = event_team & rule_team if rule_team else event_team
            if not effective_team:
                team_mismatch += 1
                self._record_event_status(event, rule, getattr(rule, "resolved_namespace", ""), "team_mismatch")
                continue
            events_by_scope.setdefault(tuple(sorted(effective_team)), []).append(event)

        self._append_outcome(
            outcomes,
            rule,
            getattr(rule, "resolved_namespace", ""),
            "team_mismatch",
            team_mismatch + missing_team,
        )

        for effective_team, scoped_events in events_by_scope.items():
            self._apply_rule_for_scope(
                rule,
                scoped_events,
                list(effective_team),
                summary,
                outcomes,
                writers,
                deadline,
            )

    def _apply_rule_for_scope(self, rule, events, effective_team, summary, outcomes, writers, deadline) -> None:  # noqa: C901
        namespace = rule.resolved_namespace
        provider_type = rule.provider_type

        key_to_events: Dict = {}
        unmatched = 0
        missing_binding = 0
        for event in events:
            if not event_matches(event, rule.match_rules):
                unmatched += 1
                continue
            params = resolve_binding(event, rule.input_binding)
            if params is None:
                missing_binding += 1
                self._record_event_status(event, rule, namespace, "missing_binding")
                continue
            binding_key = build_binding_key(params)
            key_to_events.setdefault(binding_key, []).append(event)

        self._append_outcome(outcomes, rule, namespace, "rule_unmatched", unmatched)
        self._append_outcome(outcomes, rule, namespace, "missing_binding", missing_binding)
        if not key_to_events:
            return

        all_keys = list(key_to_events)
        cache_config = dict(rule.provider_config or {})
        cache_config["_authorized_team_ids"] = effective_team
        records_by_key: Dict = {}
        status_by_key: Dict = {}
        miss_keys = []
        for binding_key in all_keys:
            cached = self._cache.get(self._cache_key(provider_type, cache_config, binding_key))
            if cached == _MISS:
                records_by_key[binding_key] = []
                status_by_key[binding_key] = "not_found"
                summary.not_found += 1
                self._record_cache_metric(provider_type, "negative_hit")
            elif cached is not None:
                records_by_key[binding_key] = cached
                status_by_key[binding_key] = "cache_hit"
                self._record_cache_metric(provider_type, "hit")
            else:
                miss_keys.append(binding_key)
                self._record_cache_metric(provider_type, "miss")

        owned_keys = []
        waiting_keys = []
        flight_tokens = {}
        for binding_key in miss_keys:
            data_cache_key = self._cache_key(provider_type, cache_config, binding_key)
            flight_key = self._singleflight_key(data_cache_key)
            token = uuid4().hex
            if self._cache.add(flight_key, token, timeout=SINGLEFLIGHT_LEASE_SECONDS):
                owned_keys.append(binding_key)
                flight_tokens[binding_key] = (flight_key, token)
            else:
                waiting_keys.append(binding_key)

        try:
            for chunk in _chunks(owned_keys, MAX_KEYS_PER_PROVIDER_CALL):
                self._fetch_chunk(
                    rule,
                    provider_type,
                    cache_config,
                    chunk,
                    records_by_key,
                    status_by_key,
                    summary,
                    outcomes,
                    deadline,
                )
        finally:
            for flight_key, token in flight_tokens.values():
                # 租约比最大 deadline 多 5 秒，正常调用结束时不会换主；仍校验 token，
                # 避免异常停顿后误删已经由下一请求取得的新租约。
                if self._cache.get(flight_key) == token:
                    self._cache.delete(flight_key)

        if waiting_keys:
            wait_deadline = min(deadline, self._clock() + SINGLEFLIGHT_WAIT_SECONDS)
            pending = list(waiting_keys)
            while pending and self._clock() < wait_deadline:
                next_pending = []
                for binding_key in pending:
                    cached = self._cache.get(self._cache_key(provider_type, cache_config, binding_key))
                    if cached == _MISS:
                        records_by_key[binding_key] = []
                        status_by_key[binding_key] = "inflight_coalesced"
                        summary.not_found += 1
                        summary.inflight_coalesced += 1
                        self._record_cache_metric(provider_type, "inflight_coalesced")
                    elif cached is not None:
                        records_by_key[binding_key] = cached
                        status_by_key[binding_key] = "inflight_coalesced"
                        summary.inflight_coalesced += 1
                        self._record_cache_metric(provider_type, "inflight_coalesced")
                    else:
                        next_pending.append(binding_key)
                pending = next_pending
                if pending:
                    self._sleeper(min(0.01, max(0, wait_deadline - self._clock())))
            if pending:
                summary.failed += len(pending)
                for binding_key in pending:
                    status_by_key[binding_key] = "inflight_coalesced"
                self._append_outcome(outcomes, rule, namespace, "inflight_coalesced", len(pending))

        rule_id = getattr(rule, "id", None)
        outcome_counts = {}
        for status in status_by_key.values():
            outcome_counts[status] = outcome_counts.get(status, 0) + 1
        for status, count in outcome_counts.items():
            if status not in {"provider_failed", "circuit_open", "budget_exhausted", "provider_saturated"}:
                self._append_outcome(outcomes, rule, namespace, status, count)
        for binding_key in all_keys:
            projected = project(records_by_key.get(binding_key, []), rule.output_projection, rule.on_multiple)
            if not projected:
                status = status_by_key.get(binding_key, "projection_empty")
                if status in {"success", "cache_hit"} and records_by_key.get(binding_key):
                    status = "projection_empty"
                for event in key_to_events[binding_key]:
                    self._record_event_status(event, rule, namespace, status)
                continue
            for event in key_to_events[binding_key]:
                enrichment = event.setdefault("enrichment", {})
                writer_key = (id(event), namespace)
                previous_rule_ids = writers.setdefault(writer_key, [])
                existing = enrichment.get(namespace)
                if not existing:
                    enrichment[namespace] = projected
                elif existing != projected:
                    enrichment[namespace], had_conflict = merge_namespace_payload(
                        existing,
                        projected,
                        rule_ids=[*previous_rule_ids, rule_id],
                    )
                    if had_conflict:
                        summary.conflict += 1
                        self._record_event_status(event, rule, namespace, "conflict")
                        logger.warning(
                            "[Enrichment] 命名空间冲突 namespace=%s rule=%s",
                            namespace,
                            getattr(rule, "name", "?"),
                        )
                if rule_id is not None and rule_id not in previous_rule_ids:
                    previous_rule_ids.append(rule_id)

                self._record_event_status(event, rule, namespace, status_by_key.get(binding_key, "success"))

    def _fetch_chunk(
        self,
        rule,
        provider_type,
        cache_config,
        keys,
        records_by_key,
        status_by_key,
        summary,
        outcomes,
        deadline,
    ) -> None:
        namespace = rule.resolved_namespace
        if self._clock() >= deadline:
            status_by_key.update({key: "budget_exhausted" for key in keys})
            summary.budget_exhausted += len(keys)
            summary.failed += len(keys)
            self._append_outcome(outcomes, rule, namespace, "budget_exhausted", len(keys))
            self._record_provider_metric(provider_type, "budget_exhausted", 0, 1)
            return

        circuit_key = self._circuit_key(provider_type, cache_config)
        decision = self._breaker.before_call(circuit_key)
        if not decision.allowed:
            status_by_key.update({key: "circuit_open" for key in keys})
            summary.circuit_open += len(keys)
            summary.failed += len(keys)
            self._append_outcome(outcomes, rule, namespace, "circuit_open", len(keys))
            self._record_provider_metric(provider_type, "circuit_open", 0, 1)
            return

        remaining = max(0, deadline - self._clock())
        if not _PROVIDER_SLOTS.acquire(timeout=remaining):
            status_by_key.update({key: "provider_saturated" for key in keys})
            summary.provider_saturated += len(keys)
            summary.failed += len(keys)
            self._append_outcome(outcomes, rule, namespace, "provider_saturated", len(keys))
            self._record_provider_metric(provider_type, "provider_saturated", 0, 1)
            return

        provider_started_at = self._clock()
        try:
            provider = get_provider(provider_type)
            call_config = dict(cache_config)
            call_config["_deadline_at"] = deadline
            try:
                fetched = provider.fetch_batch(keys, call_config)
            except Exception:
                logger.error("[Enrichment] Provider 查询失败 provider_type=%s", provider_type, exc_info=True)
                fetched = FetchBatchResult(records={}, failed_keys=set(keys))
        finally:
            _PROVIDER_SLOTS.release()

        if isinstance(fetched, FetchBatchResult):
            failed_keys = set(fetched.failed_keys)
            budget_exhausted_keys = set(fetched.budget_exhausted_keys)
            fetched_records = fetched.records
        else:
            failed_keys = set()
            budget_exhausted_keys = set()
            fetched_records = fetched
        transition = self._breaker.after_call(circuit_key, decision, success=not failed_keys)
        self._record_circuit_transition(provider_type, transition)
        provider_status = "budget_exhausted" if failed_keys and failed_keys == budget_exhausted_keys else ("failed" if failed_keys else "success")
        self._record_provider_metric(
            provider_type,
            provider_status,
            max(0, int((self._clock() - provider_started_at) * 1000)),
            1,
        )

        if failed_keys:
            summary.failed += len(failed_keys)
            ordinary_failures = failed_keys - budget_exhausted_keys
            summary.budget_exhausted += len(budget_exhausted_keys)
            self._append_outcome(outcomes, rule, namespace, "provider_failed", len(ordinary_failures))
            self._append_outcome(
                outcomes,
                rule,
                namespace,
                "budget_exhausted",
                len(budget_exhausted_keys),
            )
        for binding_key in keys:
            records = fetched_records.get(binding_key) or []
            records_by_key[binding_key] = records
            if binding_key in failed_keys:
                status_by_key[binding_key] = "budget_exhausted" if binding_key in budget_exhausted_keys else "provider_failed"
                continue
            if not records:
                summary.not_found += 1
                status_by_key[binding_key] = "not_found"
            else:
                status_by_key[binding_key] = "success"
            self._cache.set(
                self._cache_key(provider_type, cache_config, binding_key),
                records or _MISS,
                CACHE_TTL_SECONDS,
            )
