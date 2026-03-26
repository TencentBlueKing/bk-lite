from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, cast
import re
from zoneinfo import ZoneInfo
from croniter import croniter
from celery import current_app
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db import transaction
from apps.alerts.aggregation.recovery.recovery_checker import AlertRecoveryChecker
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.models import Level, Event, Alert
from apps.alerts.constants import (
    EventAction,
    AlarmStrategyType,
    AlertStatus,
    SessionStatus,
    HeartbeatStatus,
    HeartbeatCheckMode,
    HeartbeatActivationMode,
)
from apps.alerts.aggregation.strategy.matcher import StrategyMatcher
from apps.alerts.aggregation.window.factory import WindowFactory
from apps.alerts.aggregation.query.builder import SQLBuilder
from apps.alerts.aggregation.engine.connection import DuckDBConnection
from apps.alerts.aggregation.builder.alert_builder import AlertBuilder
from apps.alerts.aggregation.builder.synthetic_alert_builder import (
    SyntheticAlertBuilder,
)
from apps.core.logger import alert_logger as logger
from apps.alerts.utils.util import str_to_md5
from apps.alerts.constants.constants import LevelType


class AggregationProcessor:
    HEARTBEAT_CRON_SOURCE_TIMEZONE = ZoneInfo("Asia/Shanghai")

    def __init__(self):
        self.sql_builder = SQLBuilder()
        self.db_conn = DuckDBConnection()

    def process_aggregation(self):
        try:
            active_strategies = self._get_active_strategies()
            if not active_strategies:
                logger.info("无活跃告警策略，跳过聚合处理")
                return

            logger.info("缺失检查任务开始")
            logger.info(f"开始处理 {len(active_strategies)} 个活跃策略")
            logger.info(
                "活跃 missing_detection 策略数量=%s",
                sum(
                    1
                    for strategy in active_strategies
                    if strategy.strategy_type == AlarmStrategyType.MISSING_DETECTION
                ),
            )

            for strategy in active_strategies:
                logger.info(f"处理策略: {strategy.name} (ID: {strategy.id})")
                self._process_strategy(strategy, timezone.now())

            logger.info("所有策略处理完成")
            logger.info("缺失检查任务结束")

        except Exception as e:
            logger.exception(f"聚合处理失败: {e}")
            raise
        finally:
            AlertBuilder.clear_event_cache()
            self.db_conn.close()

    def _get_active_strategies(self) -> List[AlarmStrategy]:
        return list(
            AlarmStrategy.objects.filter(
                is_active=True,
            ).order_by("-updated_at")
        )

    @staticmethod
    def get_events_for_strategy(strategy: AlarmStrategy, now: datetime):
        """
        根据策略配置获取事件
        每个策略有自己的时间窗口和过滤条件
        """
        params = cast(Dict[str, Any], strategy.params or {})
        window_size = params.get("window_size", 10)

        cutoff_time = now - timedelta(minutes=window_size)

        logger.info(
            f"策略 {strategy.name}: 查询时间窗口={window_size}分钟, "
            f"起始时间={cutoff_time.isoformat()}"
        )

        events = Event.objects.filter(
            received_at__gte=cutoff_time,
            action__in=[EventAction.CREATED, EventAction.CLOSED],
        )

        logger.debug(f"策略 {strategy.name}: 时间范围内事件总数={events.count()}")

        return events

    def _process_strategy(self, strategy: AlarmStrategy, now: datetime):
        logger.debug(
            "策略分派路径: strategy_id=%s, strategy_type=%s",
            strategy.id,
            strategy.strategy_type,
        )

        if strategy.strategy_type == AlarmStrategyType.MISSING_DETECTION:
            self._process_missing_detection_strategy(strategy, now)
            return

        try:
            events = self.get_events_for_strategy(strategy, now)

            if not events.exists():
                logger.info(f"策略 {strategy.name}: 无事件需要处理")
                return

            matched_events = StrategyMatcher.match_events_to_strategy(
                events, cast(List[List[Dict]], strategy.match_rules or [])
            )

            if not matched_events.exists():
                logger.info(f"策略 {strategy.name}: 无匹配规则的事件")
                return

            params = cast(Dict[str, Any], strategy.params or {})
            dimensions = params.get("group_by", []) or ["event_id"]
            logger.info(f"策略 {strategy.name}: 聚合维度={dimensions}")

            if self._aggregate_for_dimensions(strategy, matched_events, dimensions, now):
                logger.info(f"策略 {strategy.name}: 维度 {dimensions} 聚合成功")

        except Exception as e:  # noqa
            logger.exception(f"策略 {strategy.name} 处理失败")

    def _process_missing_detection_strategy(
        self, strategy: AlarmStrategy, now: datetime
    ) -> None:
        logger.info(
            "单策略开始处理: strategy_id=%s, name=%s",
            strategy.id,
            strategy.name,
        )
        try:
            with transaction.atomic(using="default"):
                strategy = AlarmStrategy.objects.select_for_update().get(pk=strategy.pk)
                params = self._load_params(strategy)
                candidates = self._query_candidate_events(strategy, now)
                matched_events = self._match_heartbeat_events(strategy, candidates)
                latest_event = matched_events.order_by("-received_at").first()

                params = self._activate_if_needed(strategy, params, latest_event, now)

                if latest_event:
                    params["last_heartbeat_time"] = latest_event.received_at.isoformat()
                    params["last_heartbeat_context"] = self._build_heartbeat_context(
                        latest_event
                    )

                    active_alert = SyntheticAlertBuilder.find_active_alert(strategy)
                    if active_alert and params.get("auto_recovery", True):
                        self._recover_missing_alert(strategy, params, now)
                        params["heartbeat_status"] = HeartbeatStatus.MONITORING
                    elif not active_alert:
                        params["heartbeat_status"] = HeartbeatStatus.MONITORING

                    self._save_runtime_state(strategy, params, now)
                    return

                deadline = self._calculate_deadline(strategy, params, now)
                if deadline is None:
                    self._save_runtime_state(strategy, params, now)
                    return

                if now <= deadline:
                    self._save_runtime_state(strategy, params, now)
                    return

                active_alert = SyntheticAlertBuilder.find_active_alert(strategy)
                if active_alert:
                    logger.debug(
                        "缺失检查策略已存在活跃告警，跳过重复创建: strategy_id=%s, alert_id=%s",
                        strategy.id,
                        active_alert.alert_id,
                    )
                    params["heartbeat_status"] = HeartbeatStatus.ALERTING
                    self._save_runtime_state(strategy, params, now)
                    return

                self._trigger_missing_alert(strategy, params, now, deadline)
                params["heartbeat_status"] = HeartbeatStatus.ALERTING
                self._save_runtime_state(strategy, params, now)
        except Exception:
            logger.exception("缺失检查策略处理失败: strategy_id=%s", strategy.id)
            raise

    @staticmethod
    def _load_params(strategy: AlarmStrategy) -> Dict[str, Any]:
        params = dict(cast(Dict[str, Any], strategy.params or {}))
        params.setdefault("check_mode", HeartbeatCheckMode.CRON)
        params.setdefault("cron_expr", "")
        params.setdefault("grace_period", 0)
        params.setdefault("activation_mode", HeartbeatActivationMode.FIRST_HEARTBEAT)
        params.setdefault("auto_recovery", True)
        params.setdefault("heartbeat_status", HeartbeatStatus.WAITING)
        params.setdefault("last_heartbeat_time", None)
        params.setdefault("last_heartbeat_context", None)
        params.setdefault("alert_template", {})
        return params

    def _query_candidate_events(self, strategy: AlarmStrategy, now: datetime):
        queryset = Event.objects.all()
        if strategy.last_execute_time:
            queryset = queryset.filter(received_at__gt=strategy.last_execute_time)
            logger.debug(
                "候选事件查询窗口: strategy_id=%s, start=%s, end=%s",
                strategy.id,
                strategy.last_execute_time.isoformat(),
                now.isoformat(),
            )
        else:
            queryset = queryset.filter(received_at__gte=strategy.created_at)
            logger.debug(
                "候选事件查询窗口: strategy_id=%s, start=%s, end=%s",
                strategy.id,
                strategy.created_at.isoformat(),
                now.isoformat(),
            )
        return queryset

    def _match_heartbeat_events(self, strategy: AlarmStrategy, candidates):
        matched_events = StrategyMatcher.match_events_to_strategy(
            candidates, cast(List[List[Dict]], strategy.match_rules or [])
        )
        logger.debug(
            "matched_events 数量: strategy_id=%s, count=%s",
            strategy.id,
            matched_events.count(),
        )
        return matched_events

    def _activate_if_needed(
        self,
        strategy: AlarmStrategy,
        params: Dict[str, Any],
        latest_event: Optional[Event],
        now: datetime,
    ) -> Dict[str, Any]:
        if params.get("heartbeat_status") != HeartbeatStatus.WAITING:
            return params

        if params.get("activation_mode") == HeartbeatActivationMode.IMMEDIATE:
            params["heartbeat_status"] = HeartbeatStatus.MONITORING
            logger.info(
                "激活状态切换: waiting -> monitoring, strategy_id=%s, mode=immediate",
                strategy.id,
            )
            return params

        if latest_event is None:
            return params

        params["heartbeat_status"] = HeartbeatStatus.MONITORING
        params["last_heartbeat_time"] = latest_event.received_at.isoformat()
        params["last_heartbeat_context"] = self._build_heartbeat_context(latest_event)
        logger.info(
            "激活状态切换: waiting -> monitoring, strategy_id=%s, mode=first_heartbeat, event_id=%s",
            strategy.id,
            latest_event.event_id,
        )
        return params

    def _calculate_deadline(
        self, strategy: AlarmStrategy, params: Dict[str, Any], now: datetime
    ) -> Optional[datetime]:
        project_tz = timezone.get_current_timezone()
        cron_tz = self.HEARTBEAT_CRON_SOURCE_TIMEZONE
        now_in_tz = self._normalize_to_project_timezone(now, project_tz)
        now_in_cron_tz = self._normalize_to_timezone(now, cron_tz)
        last_heartbeat_time = self._parse_runtime_datetime(
            params.get("last_heartbeat_time")
        )
        last_heartbeat_in_tz = self._normalize_to_project_timezone(
            last_heartbeat_time, project_tz
        )
        last_heartbeat_in_cron_tz = self._normalize_to_timezone(
            last_heartbeat_time, cron_tz
        )

        if params.get("activation_mode") == HeartbeatActivationMode.IMMEDIATE:
            monitoring_start = self._normalize_to_project_timezone(
                strategy.created_at, project_tz
            )
            monitoring_start_in_cron_tz = self._normalize_to_timezone(
                strategy.created_at, cron_tz
            )
        else:
            monitoring_start = last_heartbeat_in_tz
            monitoring_start_in_cron_tz = last_heartbeat_in_cron_tz

        if monitoring_start is None or monitoring_start_in_cron_tz is None:
            return None

        grace_period = timedelta(minutes=int(params.get("grace_period") or 0))

        try:
            cron_expr = str(params.get("cron_expr") or "")
            first_expected_in_cron_tz = self._normalize_to_timezone(
                croniter(cron_expr, monitoring_start_in_cron_tz).get_next(datetime),
                cron_tz,
            )
            first_expected = self._normalize_to_project_timezone(
                first_expected_in_cron_tz, project_tz
            )
            if first_expected is None:
                return None

            if now_in_tz < first_expected:
                deadline = first_expected + grace_period
                logger.debug(
                    "deadline 计算结果: strategy_id=%s, now=%s, monitoring_start=%s, first_expected=%s, deadline=%s, project_timezone=%s, cron_timezone=%s",
                    strategy.id,
                    now_in_tz.isoformat(),
                    monitoring_start.isoformat(),
                    first_expected.isoformat(),
                    deadline.isoformat(),
                    project_tz,
                    cron_tz,
                )
                return deadline

            previous_expected_in_cron_tz = self._normalize_to_timezone(
                croniter(cron_expr, now_in_cron_tz).get_prev(datetime), cron_tz
            )
            previous_expected = self._normalize_to_project_timezone(
                previous_expected_in_cron_tz, project_tz
            )
            if previous_expected is None:
                return None

            if last_heartbeat_in_tz and last_heartbeat_in_tz >= previous_expected:
                next_expected_in_cron_tz = self._normalize_to_timezone(
                    croniter(cron_expr, previous_expected_in_cron_tz).get_next(
                        datetime
                    ),
                    cron_tz,
                )
                next_expected = self._normalize_to_project_timezone(
                    next_expected_in_cron_tz,
                    project_tz,
                )
                if next_expected is None:
                    return None
                deadline = next_expected + grace_period
                logger.debug(
                    "deadline 计算结果: strategy_id=%s, now=%s, last_heartbeat=%s, previous_expected=%s, next_expected=%s, deadline=%s, project_timezone=%s, cron_timezone=%s",
                    strategy.id,
                    now_in_tz.isoformat(),
                    last_heartbeat_in_tz.isoformat(),
                    previous_expected.isoformat(),
                    next_expected.isoformat(),
                    deadline.isoformat(),
                    project_tz,
                    cron_tz,
                )
                return deadline

            deadline = previous_expected + grace_period
        except Exception:
            logger.exception("cron 表达式解析失败: strategy_id=%s", strategy.id)
            raise

        logger.debug(
            "deadline 计算结果: strategy_id=%s, now=%s, monitoring_start=%s, last_heartbeat=%s, previous_expected=%s, deadline=%s, project_timezone=%s, cron_timezone=%s",
            strategy.id,
            now_in_tz.isoformat(),
            monitoring_start.isoformat(),
            last_heartbeat_in_tz.isoformat() if last_heartbeat_in_tz else "",
            previous_expected.isoformat(),
            deadline.isoformat(),
            project_tz,
            cron_tz,
        )
        return deadline

    def _trigger_missing_alert(
        self,
        strategy: AlarmStrategy,
        params: Dict[str, Any],
        now: datetime,
        deadline: Optional[datetime],
    ) -> Optional[Alert]:
        alert = SyntheticAlertBuilder.create_alert(strategy, params, now)
        logger.info(
            "触发缺失告警: strategy_id=%s, alert_id=%s, deadline=%s",
            strategy.id,
            alert.alert_id,
            deadline.isoformat() if deadline else "",
        )
        return alert

    def _recover_missing_alert(
        self,
        strategy: AlarmStrategy,
        params: Dict[str, Any],
        now: datetime,
    ) -> Optional[Alert]:
        active_alert = SyntheticAlertBuilder.find_active_alert(strategy)
        if not active_alert:
            return None

        active_alert.status = AlertStatus.AUTO_RECOVERY
        active_alert.last_event_time = now
        active_alert.save(update_fields=["status", "last_event_time", "updated_at"])

        from apps.alerts.service.reminder_service import ReminderService

        ReminderService.stop_reminder_task(active_alert)
        logger.info(
            "自动恢复成功: strategy_id=%s, alert_id=%s",
            strategy.id,
            active_alert.alert_id,
        )
        return active_alert

    def _save_runtime_state(
        self,
        strategy: AlarmStrategy,
        params: Dict[str, Any],
        now: datetime,
    ) -> None:
        strategy.params = params
        strategy.last_execute_time = now
        strategy.save(update_fields=["params", "last_execute_time", "updated_at"])

    @staticmethod
    def _build_heartbeat_context(event: Event) -> Dict[str, Any]:
        return {
            "service": event.service,
            "location": event.location,
            "resource_name": event.resource_name,
            "resource_id": event.resource_id,
            "resource_type": event.resource_type,
            "item": event.item,
            "title": event.title,
            "level": event.level,
        }

    @staticmethod
    def _parse_runtime_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        parsed = parse_datetime(value)
        if parsed is None:
            parsed = datetime.fromisoformat(value)
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed

    @staticmethod
    def _normalize_to_project_timezone(
        value: Optional[datetime], project_tz=None
    ) -> Optional[datetime]:
        if value is None:
            return None
        tz = project_tz or timezone.get_current_timezone()
        if timezone.is_naive(value):
            return timezone.make_aware(value, tz)
        return timezone.localtime(value, tz)

    @staticmethod
    def _normalize_to_timezone(
        value: Optional[datetime], target_tz
    ) -> Optional[datetime]:
        if value is None:
            return None
        if timezone.is_naive(value):
            return timezone.make_aware(value, target_tz)
        return timezone.localtime(value, target_tz)

    def _aggregate_for_dimensions(
        self,
        strategy: AlarmStrategy,
        events,
        dimensions: List[str],
        now: datetime,
    ) -> bool:
        """对指定维度执行聚合"""
        try:
            # 优化：直接使用已过滤的 events QuerySet，避免重复查询
            load_success = self.db_conn.load_events_to_memory(events)
            if not load_success:
                logger.info(f"策略 {strategy.name}过滤后无事件，跳过聚合")
                return False

            window_config = WindowFactory.create_from_strategy(strategy)

            logger.debug(
                f"策略 {strategy.name}: 窗口配置 "
                f"type={window_config.window_type}, "
                f"size={window_config.window_size_minutes}分钟"
            )

            sql_query = self.sql_builder.build_aggregation_sql(
                dimensions=dimensions,
                window_config=window_config,
                strategy_id=strategy.id,
            )

            logger.debug(f"策略 {strategy.name}: 执行聚合SQL")

            results = self.db_conn.execute_query(sql_query)

            if not results:
                logger.info(f"策略 {strategy.name}: 聚合结果为空")
                return False

            logger.info(f"策略 {strategy.name}: 聚合完成, 生成 {len(results)} 个告警组")

            success_count = self._create_or_update_alerts(results, strategy, dimensions)
            if success_count > 0:
                self._mark_strategy_executed(strategy, now)
            return True

        except Exception as e:
            logger.error(
                f"策略 {strategy.name}: 维度 {dimensions} 聚合失败: {e}", exc_info=True
            )
            return False

    def _create_or_update_alerts(
        self,
        aggregation_results: List[Dict[str, Any]],
        strategy: AlarmStrategy,
        dimensions: List[str],
    ) -> int:
        """创建或更新告警"""

        logger.info(
            f"策略 {strategy.name}: 开始创建/更新告警, "
            f"结果数={len(aggregation_results)}"
        )
        alert_levels = list(
            Level.objects.filter(level_type=LevelType.ALERT).values(
                "level_id", "level_name", "level_display_name"
            )
        )
        success_count = 0
        fail_count = 0
        recovered_count = 0
        new_alert_ids = []  # 收集新创建的告警ID

        for result in aggregation_results:
            try:
                self._normalize_fingerprint(result, alert_levels)
                with transaction.atomic():
                    # 记录是否为新创建的告警
                    fingerprint = result.get("fingerprint")
                    is_new_alert = not self._is_existing_alert(fingerprint)

                    alert = AlertBuilder.create_or_update_alert(
                        aggregation_result=result,
                        strategy=strategy,
                        group_by_field=",".join(dimensions),
                    )

                    # 如果是新创建的告警，记录ID用于后续自动分配
                    if is_new_alert:
                        should_delay_assignment = (
                            alert.is_session_alert
                            and alert.session_status == SessionStatus.OBSERVING
                        )

                        if should_delay_assignment:
                            logger.info(
                                "策略 %s: 新建会话窗口告警 %s 仍在观察期，等待超时确认后再自动分派",
                                strategy.name,
                                alert.alert_id,
                            )
                        else:
                            new_alert_ids.append(alert.alert_id)

                    # 检查是否应该自动恢复
                    if AlertRecoveryChecker.check_and_recover_alert(alert):
                        recovered_count += 1

                    success_count += 1
                    logger.debug(
                        f"策略 {strategy.name}: 告警处理成功 "
                        f"fingerprint={result.get('fingerprint')}"
                    )
            except Exception as e:
                fail_count += 1
                logger.error(
                    f"策略 {strategy.name}: 告警创建/更新失败 "
                    f"fingerprint={result.get('fingerprint')}: {e}",
                    exc_info=True,
                )

        logger.info(
            f"策略 {strategy.name}: 告警处理完成, "
            f"成功={success_count}, 失败={fail_count}, 自动恢复={recovered_count}"
        )
        # 异步执行新创建告警的自动分配（不阻塞聚合流程）
        if new_alert_ids:
            self._schedule_auto_assignment(new_alert_ids)

        return success_count

    @staticmethod
    def _mark_strategy_executed(strategy: AlarmStrategy, now: datetime) -> None:
        strategy.last_execute_time = now
        strategy.save(update_fields=["last_execute_time", "updated_at"])

    @staticmethod
    def _normalize_fingerprint(result: Dict[str, Any], alert_levels) -> None:
        fingerprint = result.get("fingerprint")
        if not fingerprint:
            return
        global_level = [str(i["level_id"]) for i in alert_levels]
        raw_fingerprint = fingerprint.split("|")[-1]
        now_level = result["alert_level"]
        event_count = int(result.get("event_count") or 0)
        first_event_description = (result.get("first_event_description") or "").strip()
        global_level = sorted(global_level)
        critical_level = [str(i) for i in [global_level[0]]]
        normal_level = [str(i) for i in global_level[1:]]
        result["fingerprint"] = str_to_md5(raw_fingerprint)
        fingerprint_is_md5 = re.fullmatch(r"[0-9a-fA-F]{32}", raw_fingerprint)

        def _build_description() -> str:
            if event_count == 1 and first_event_description:
                return first_event_description
            return f"影响范围：{result['alert_description']}"

        if str(now_level) in critical_level:
            if not fingerprint_is_md5:
                result["alert_title"] = f"{raw_fingerprint} 发生严重问题"
                result["alert_description"] = _build_description()
        if str(now_level) in normal_level:
            if not fingerprint_is_md5:
                result["alert_title"] = f"{raw_fingerprint} 检测到异常"
                result["alert_description"] = _build_description()

    @staticmethod
    def _is_existing_alert(fingerprint: str) -> bool:
        """
        检查指定指纹的活跃告警是否已存在

        Args:
            fingerprint: 告警指纹

        Returns:
            bool: 存在返回True，否则返回False
        """
        return Alert.objects.filter(
            fingerprint=fingerprint, status__in=AlertStatus.ACTIVATE_STATUS
        ).exists()

    @staticmethod
    def _schedule_auto_assignment(alert_ids: List[str]) -> None:
        """
        调度告警自动分配任务（异步）

        使用Celery异步任务，避免阻塞聚合流程

        Args:
            alert_ids: 新创建的告警ID列表
        """
        try:
            from apps.alerts.tasks import async_auto_assignment_for_alerts

            logger.info(f"调度自动分配任务，告警数量: {len(alert_ids)}")
            current_app.send_task(
                async_auto_assignment_for_alerts.name, args=[alert_ids]
            )
            logger.debug(f"自动分配任务已提交到队列")

        except Exception as e:  # noqa
            logger.exception("调度自动分配任务失败")
            # 调度失败不影响聚合主流程
