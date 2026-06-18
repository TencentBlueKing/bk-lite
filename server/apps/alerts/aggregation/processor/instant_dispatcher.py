"""即时告警旁路调度器。

接在 ``AlertSourceAdapter.main()`` 内 ``create_events`` 之后调用，与现有
"Beat → DuckDB 聚合"管线**并行**。本模块仅处理 ``strategy_type == INSTANT``
的策略；聚合管线已通过 ``AggregationProcessor._get_active_strategies`` 排除
INSTANT 策略，两条路径完全互斥。

性能取舍：1-event-per-call 主场景下 Celery 中转是纯开销，因此命中数
``<= INSTANT_SYNC_THRESHOLD`` 时同步 ``bulk_create``；超阈值才退化到 Celery
``build_instant_alerts`` 任务，以应对单次调用塞入大批事件的边界场景。
"""

import hashlib
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional

from celery import current_app
from django.db import transaction

from apps.alerts.constants import (
    EventAction,
    INSTANT_HIT_CEILING,
    INSTANT_STRATEGY_CACHE_TTL,
    INSTANT_SYNC_THRESHOLD,
)
from apps.alerts.constants.constants import AlarmStrategyType, AlertStatus, EventStatus
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.models import Alert, Event
from apps.alerts.utils.permission_scope import normalize_team_ids
from apps.core.logger import alert_logger as logger


@dataclass(slots=True)
class InstantHit:
    """单条命中记录：(策略 id, 事件 id)"""

    strategy_id: int
    event_id: str


class InstantStrategyCache:
    """active INSTANT 策略的进程内 TTL 缓存。

    多 worker 间最坏 ``INSTANT_STRATEGY_CACHE_TTL`` 秒不一致；策略变更非
    高频，可接受。Strategy serializer save 后会主动调用 ``cache_clear``。
    """

    _value: Optional[List[AlarmStrategy]] = None
    _cached_at: float = 0.0

    @classmethod
    def get(cls) -> List[AlarmStrategy]:
        now = time.monotonic()
        if cls._value is not None and (now - cls._cached_at) < INSTANT_STRATEGY_CACHE_TTL:
            return cls._value
        value = list(
            AlarmStrategy.objects.filter(
                is_active=True,
                strategy_type=AlarmStrategyType.INSTANT,
            )
        )
        cls._value = value
        cls._cached_at = now
        logger.debug("instant strategy cache refreshed: count=%s", len(value))
        return value

    @classmethod
    def cache_clear(cls) -> None:
        cls._value = None
        cls._cached_at = 0.0


def _build_fingerprint(strategy_id: int, event_id: str) -> str:
    """``md5("instant:<sid>:<eid>")``。

    与聚合指纹命名空间完全隔离，碰撞概率极低；同时保证同一 (sid, eid) 重复
    投递时指纹固定，配合 ``bulk_create(ignore_conflicts=True)`` 天然幂等。
    """
    raw = f"instant:{strategy_id}:{event_id}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _render_template(template: Optional[str], event: Event) -> str:
    """极简模板渲染。支持 ``{service}`` / ``{location}`` / ``{resource_name}``
    / ``{resource_id}`` / ``{resource_type}`` / ``{item}`` / ``{title}`` /
    ``{level}`` / ``{external_id}`` 等事件标准字段。

    模板缺失或渲染失败时返回原始字符串（或空串）；渲染异常仅记 DEBUG，避免
    单条事件渲染失败拖垮整批。
    """
    if not template:
        return ""
    context = {
        "service": event.service or "",
        "location": event.location or "",
        "resource_name": event.resource_name or "",
        "resource_id": event.resource_id or "",
        "resource_type": event.resource_type or "",
        "item": event.item or "",
        "title": event.title or "",
        "level": event.level or "",
        "external_id": event.external_id or "",
    }
    try:
        return template.format(**context)
    except (KeyError, IndexError, ValueError):
        logger.debug("instant template render skipped due to invalid placeholder")
        return template


def _safe_team(strategy: AlarmStrategy) -> List:
    try:
        return normalize_team_ids(strategy.dispatch_team) or []
    except ValueError:
        return []


def _build_alert_row(strategy: AlarmStrategy, event: Event, fingerprint: str) -> Alert:
    """根据 event 构造 Alert 实例（未入库）。

    - level 强制继承 event.level（PRD: 告警级别 = 事件级别）
    - 标题/描述：用户配置了 alert_template 则渲染，否则取事件原始文案（原汁原味）
    - event_count = 1（即时告警恒定）
    """
    params = strategy.params or {}
    template = params.get("alert_template") or {}
    rendered_title = _render_template(template.get("title"), event) or (event.title or "即时告警")
    rendered_desc = _render_template(template.get("description"), event) or (event.description or "")

    return Alert(
        alert_id=f"ALERT-{uuid.uuid4().hex.upper()}",
        fingerprint=fingerprint,
        rule_id=str(strategy.id),
        group_by_field="instant",
        status=AlertStatus.UNASSIGNED,
        level=str(event.level) if event.level is not None else "",
        title=rendered_title,
        content=rendered_desc,
        first_event_time=event.received_at,
        last_event_time=event.received_at,
        item=event.item,
        resource_id=event.resource_id,
        resource_name=event.resource_name,
        resource_type=event.resource_type,
        source_name=getattr(getattr(event, "source", None), "name", None),
        labels=event.labels or {},
        team=_safe_team(strategy),
    )


def _bulk_build_instant_alerts(hits: List[InstantHit]) -> List[str]:
    """按 strategy_id 分桶 bulk_create Alert + M2M。

    供同步路径与 Celery 异步任务共用。返回**本次实际新建**的 alert_id 列表
    （已存在指纹被 ``ignore_conflicts`` 跳过，不进列表，避免重复触发分派）。
    """
    if not hits:
        return []

    all_sids = {h.strategy_id for h in hits}
    all_eids = {h.event_id for h in hits}

    strategies = AlarmStrategy.objects.in_bulk(all_sids)
    events = {e.event_id: e for e in Event.objects.select_related("source").filter(event_id__in=all_eids)}

    by_sid: dict = defaultdict(list)
    for hit in hits:
        evt = events.get(hit.event_id)
        strat = strategies.get(hit.strategy_id)
        if evt is None or strat is None:
            continue
        by_sid[hit.strategy_id].append(evt)

    created_alert_ids: List[str] = []
    for sid, evt_list in by_sid.items():
        strategy = strategies[sid]
        # 1) 计算本桶所有目标指纹，并过滤已存在的活跃指纹（幂等保证）
        all_fps = [_build_fingerprint(sid, evt.event_id) for evt in evt_list]
        existing_fps = set(
            Alert.objects.filter(
                fingerprint__in=all_fps,
                status__in=AlertStatus.ACTIVATE_STATUS,
            ).values_list("fingerprint", flat=True)
        )
        new_events_with_fp = [
            (evt, fp) for evt, fp in zip(evt_list, all_fps) if fp not in existing_fps
        ]
        if not new_events_with_fp:
            continue

        alerts_to_create: List[Alert] = []
        fp_to_event: dict = {}
        for evt, fp in new_events_with_fp:
            alerts_to_create.append(_build_alert_row(strategy, evt, fp))
            fp_to_event[fp] = evt

        try:
            with transaction.atomic():
                Alert.objects.bulk_create(alerts_to_create, ignore_conflicts=True)
                # 回查实际入库的 Alert（兼容 MySQL bulk_create 不回填 pk 的情况）
                wanted_alert_ids = {a.alert_id for a in alerts_to_create}
                created = list(
                    Alert.objects.filter(alert_id__in=wanted_alert_ids).values_list(
                        "id", "alert_id", "fingerprint"
                    )
                )
                m2m_rows = []
                for alert_pk, alert_id, fp in created:
                    evt = fp_to_event.get(fp)
                    if evt is None:
                        continue
                    m2m_rows.append(
                        Alert.events.through(alert_id=alert_pk, event_id=evt.id)
                    )
                    created_alert_ids.append(alert_id)
                if m2m_rows:
                    Alert.events.through.objects.bulk_create(m2m_rows, ignore_conflicts=True)
        except Exception:
            logger.exception(
                "instant bulk_build failed: strategy_id=%s event_count=%s",
                sid,
                len(evt_list),
            )

    return created_alert_ids


def _trigger_dispatch_async(alert_ids: List[str]) -> None:
    if not alert_ids:
        return
    try:
        # 用符号引用任务名，避免硬编码字符串在重命名/挪模块时静默失效
        from apps.alerts.tasks import async_auto_assignment_for_alerts

        current_app.send_task(
            async_auto_assignment_for_alerts.name,
            args=[alert_ids],
        )
    except Exception:
        logger.exception("instant dispatch trigger send_task failed: count=%s", len(alert_ids))


class InstantAlertDispatcher:
    """旁路调度入口。

    本类不持有状态，所有方法均为 staticmethod；其内部异常都会被 ``dispatch``
    捕获并记日志，**绝不**向上抛出，从而不影响 ``AlertSourceAdapter.main()``
    的现有主流程。
    """

    @staticmethod
    def dispatch(bulk_events) -> None:
        """主入口。

        :param bulk_events: ``AlertSourceAdapter.create_events`` 的返回值
            （按批分组的 Event 实例二维列表）。
        """
        try:
            strategies = InstantStrategyCache.get()
            if not strategies:
                return

            events: List[Event] = []
            for batch in bulk_events or []:
                for evt in batch or []:
                    if getattr(evt, "action", None) == EventAction.CREATED:
                        events.append(evt)
            if not events:
                return

            # 跳过已被屏蔽的事件（事件级·不建警）。屏蔽在 main() 中先于 dispatch 执行，
            # 但更新落在 DB，内存对象 status 仍为旧值，故按 event_id 回查最新 SHIELD 状态。
            shielded_ids = set(
                Event.objects.filter(
                    event_id__in=[e.event_id for e in events],
                    status=EventStatus.SHIELD,
                ).values_list("event_id", flat=True)
            )
            if shielded_ids:
                events = [e for e in events if e.event_id not in shielded_ids]
                if not events:
                    return

            hits = InstantAlertDispatcher._collect_hits(events, strategies)
            if not hits:
                return

            logger.info(
                "instant dispatch: events=%s strategies=%s hits=%s",
                len(events),
                len(strategies),
                len(hits),
            )

            if len(hits) <= INSTANT_SYNC_THRESHOLD:
                alert_ids = _bulk_build_instant_alerts(hits)
                if alert_ids:
                    logger.info("instant sync created alerts=%s", len(alert_ids))
                    _trigger_dispatch_async(alert_ids)
            else:
                payload = [
                    {"strategy_id": h.strategy_id, "event_id": h.event_id} for h in hits
                ]
                try:
                    from apps.alerts.tasks import build_instant_alerts

                    current_app.send_task(build_instant_alerts.name, args=[payload])
                    logger.info("instant async enqueued hits=%s", len(payload))
                except Exception:
                    logger.exception("instant async send_task failed; fallback to sync")
                    alert_ids = _bulk_build_instant_alerts(hits)
                    _trigger_dispatch_async(alert_ids)
        except Exception:
            logger.exception("instant dispatch failed; main pipeline unaffected")

    @staticmethod
    def _collect_hits(
        events: List[Event], strategies: List[AlarmStrategy]
    ) -> List[InstantHit]:
        from apps.alerts.aggregation.strategy.instant_matcher import InstantMatcher

        hits: List[InstantHit] = []
        for event in events:
            for strategy in strategies:
                if InstantMatcher.match_in_memory(event, strategy.match_rules or []):
                    hits.append(InstantHit(strategy.id, event.event_id))
                    if len(hits) >= INSTANT_HIT_CEILING:
                        logger.error(
                            "instant hits truncated at ceiling=%s", INSTANT_HIT_CEILING
                        )
                        return hits
        return hits
