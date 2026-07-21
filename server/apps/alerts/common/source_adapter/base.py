# -- coding: utf-8 --
# @File: base.py
# @Time: 2025/5/13 15:48
# @Author: windyzhao
import datetime
import uuid
import hashlib
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from django.db import IntegrityError
from django.db.models import Prefetch

from django.utils import timezone

from apps.alerts.aggregation.recovery.recovery_handler import RecoveryHandler
from apps.alerts.common.shield import execute_shield_check_for_events
from apps.alerts.constants.constants import LevelType, EventAction, AlertStatus, SNMP_TRAP_SOURCE_ID, DEFAULT_GROUP_ID
from apps.alerts.error import AuthenticationSourceError
from apps.alerts.models.models import Alert, Event, Level
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.common.source_adapter import logger
from apps.alerts.utils.util import decode_team_secret, split_list
from apps.alerts.utils.permission_scope import normalize_team_ids
from apps.alerts.enrichment.engine import EnrichmentEngine
from apps.rpc.cmdb import CMDB


class AlertSourceAdapter(ABC):
    """告警源适配器基类"""

    def __init__(self, alert_source: AlertSource, secret: str = None, events: Optional[List] = None, trusted_internal: bool = False):
        self.alert_source = alert_source
        self.config = alert_source.config
        self.secret = secret
        self.events = events or []
        # 可信内部推送（如监控中心经 NATS 内部源直推）：采信 event 自带的 organizations 作为归属组织，
        # 不走组织级 secret 解析。仅影响内部通道，外部告警源安全模型不变。
        self.trusted_internal = trusted_internal
        self.mapping = self.alert_source.config.get("event_fields_mapping", {})
        self.unique_fields = ["title"]
        self.info_level, self.levels = self.get_event_level()
        self.resolved_team = self._resolve_team_from_secret(secret)
        self.team_secrets = set(self.alert_source.team_secrets.values())

    def _resolve_team_from_secret(self, secret: str) -> List:
        if not secret:
            return []
        team_secrets = getattr(self.alert_source, "team_secrets", None) or {}
        for team_id, team_secret in team_secrets.items():
            if team_secret != secret:
                continue
            payload = decode_team_secret(team_secret)
            if not payload:
                continue
            if payload.get("source_secret") != self.alert_source.secret:
                continue
            payload_team_id = payload.get("team_id")
            if payload_team_id not in {str(team_id), team_id}:
                continue
            try:
                return [int(payload_team_id)]
            except (TypeError, ValueError):
                try:
                    return [int(team_id)]
                except (TypeError, ValueError):
                    return [team_id]
        return []

    @staticmethod
    def get_event_level() -> tuple:
        """获取事件级别"""
        instance = list(
            Level.objects.filter(level_type=LevelType.EVENT).order_by("level_id").values_list("level_id", flat=True))

        return str(max(instance)), [str(i) for i in instance]

    @staticmethod
    def enable_enrich() -> bool:
        return False

    @staticmethod
    def enrich_event(data: Dict[str, Any]) -> None:
        resource_type = data.get("resource_type")
        resource_id = data.get("resource_id")
        if not resource_type or not resource_id:
            return

        params = {"model_id": resource_type, "_id": resource_id}
        try:
            try:
                resource = CMDB().search_instances(**params)
            except TypeError:
                resource = CMDB().search_instances(params)
        except Exception:
            logger.error("[AlertSource] 单事件 CMDB 丰富失败: %s", params, exc_info=True)
            return

        if isinstance(resource, dict) and resource:
            data.setdefault("labels", {}).update(resource)

    def rich_event(self, data: Dict[str, Any]) -> None:
        if not getattr(self, "enable_rich_event", self.enable_enrich()):
            return
        self.enrich_event(data)

    def authenticate(self) -> bool:
        # 契约：认证通过返回 True，否则抛 AuthenticationSourceError（不会返回 False）。
        if self.secret in self.team_secrets:
            # secret 命中 team_secrets，但无法据此解析归属组织（如源级 secret 轮换后
            # team_secrets 未同步重算）→ 拒绝，避免产生 team=[] 的孤儿事件。
            if not self.resolved_team:
                logger.warning(
                    "[AlertSource] secret 命中 team_secrets 但无法解析归属组织，拒绝接入: source_id=%s",
                    self.alert_source.source_id,
                )
                raise AuthenticationSourceError("Authentication failed: cannot resolve team for secret")
            return True
        # SNMP Trap 暂不参与组织级 secret 路由：bridge 用源级 secret 接入即可，事件统一归默认组织。
        # 后续迭代再做按 trap 内容/节点的精细归属，参考日志模块的 LogGroup 规则模型。
        if (
            self.alert_source.source_id == SNMP_TRAP_SOURCE_ID
            and self.secret
            and self.secret == self.alert_source.secret
        ):
            self.resolved_team = [DEFAULT_GROUP_ID]
            return True
        raise AuthenticationSourceError("Authentication failed")

    @abstractmethod
    def fetch_alerts(self) -> List[Dict[str, Any]]:
        """从告警源获取告警数据"""
        pass

    def normalize_payload(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """将上游原始 payload 规范化为标准事件列表"""
        events = payload.get("events", [])
        if not isinstance(events, list) or not events:
            raise ValueError("Missing events.")
        return events

    def get_integration_guide(self, base_url: str) -> Dict[str, Any]:
        """返回源类型对接说明与模板"""
        # 对于 snmp_trap 这类内置 source，接入地址可能不是通用 receiver_data，
        # 因此这里优先读取 source 自身配置的 url，避免说明文档和真实入口不一致。
        webhook_path = self.alert_source.config.get("url") or "/api/v1/alerts/api/receiver_data/"
        description = self.alert_source.config.get("description") or "通用事件接收入口"
        return {
            "source_type": self.alert_source.source_type,
            "source_id": self.alert_source.source_id,
            "webhook_url": f"{base_url}{webhook_path}",
            "headers": {"SECRET": self.alert_source.secret},
            "description": description,
        }

    @staticmethod
    def build_external_id_from_fields(data: Dict[str, Any], fields: List[str]) -> str:
        fingerprint_data = {}
        for field in fields:
            value = data.get(field)
            fingerprint_data[field] = str(value).strip() if value is not None and str(value).strip() else "unknown"
        return hashlib.md5(json.dumps(fingerprint_data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def mapping_fields_to_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """将告警字段映射到事件字段"""
        result = {}
        for key, field in self.mapping.items():
            _value = event.get(field, None)
            if key in self.unique_fields:
                # 如果是唯一字段但是没有传递 丢弃
                if not _value:
                    return {}
            elif key == "level":
                # 如果是级别字段没有传递默认给 info
                if not _value or _value not in self.levels:
                    _value = self.info_level
            else:
                if not _value and _value != 0:
                    # 去元数据里找
                    label = event.get("labels", {})
                    _value = label.get(field, None)
                    if not _value:
                        # 如果元数据里也没有，直接跳过
                        continue

            if _value and (key == "start_time" or key == "end_time"):
                _value = self.timestamp_to_datetime(_value)

            if key == "value":
                _value = float(_value) if _value and isinstance(_value, str) and _value.isdigit() else _value

            result[key] = _value

        self.add_start_time(result)

        return result

    @staticmethod
    def add_start_time(data):
        if "start_time" not in data or not data.get("start_time"):
            # 如果没有开始时间，默认使用当前时间，并标记为"系统补全"（供幂等键按分钟截断，见 1-2）
            data["start_time"] = timezone.now()
            data["_start_time_synthesized"] = True

    def create_events(self, add_events):
        """将原始告警数据转换为Event对象（批量丰富）"""
        event_dicts = []
        skipped_missing = 0  # 预期内丢弃：缺必填字段
        errored = 0  # 非预期错误：转换异常
        for add_event in add_events:
            try:
                data = self.mapping_fields_to_event(add_event)
                if not data:
                    # 缺少必填字段（如 title）→ 丢弃，避免构造出 start_time=None 的空事件，
                    # 否则会在 bulk_create 时因 NOT NULL 约束令整批写入失败。
                    skipped_missing += 1
                    logger.warning("[AlertSource] 事件缺少必填字段，已跳过: %s", add_event)
                    continue
                data["team"] = self._resolve_event_team(add_event)
                data.setdefault("enrichment", {})
                event_dicts.append((data, add_event))
            except Exception as e:
                errored += 1
                logger.error("[AlertSource] 事件映射失败: %s, error: %s", add_event, e, exc_info=True)

        # 整批丰富（尽力而为，内部已隔离异常）
        try:
            EnrichmentEngine().enrich_batch([d for d, _ in event_dicts])
        except Exception:
            logger.error("[AlertSource] 批量丰富失败，跳过", exc_info=True)

        events = []
        for data, add_event in event_dicts:
            try:
                # 取出"系统补全 start_time"标记（非模型字段，不能传入 Event(**data)）
                synthesized = data.pop("_start_time_synthesized", False)
                event = Event(**data)
                event._start_time_synthesized = synthesized
                self.add_base_fields(event, add_event)
                events.append(event)
            except Exception as e:
                errored += 1
                logger.error("[AlertSource] 事件转换失败: %s, error: %s", add_event, e, exc_info=True)
        # D3：让接入过程中的丢弃可观测，区分"预期跳过"与"非预期错误"，避免静默丢数据。
        if skipped_missing or errored:
            logger.warning(
                "[AlertSource] 接入丢弃统计: source_id=%s received=%s transformed=%s skipped_missing=%s errored=%s",
                self.alert_source.source_id, len(add_events), len(events), skipped_missing, errored,
            )
        else:
            logger.info(
                "[AlertSource] 接入转换完成: source_id=%s received=%s transformed=%s",
                self.alert_source.source_id, len(add_events), len(events),
            )
        bulk_events = self.bulk_save_events(events)
        accepted = sum(len(batch or []) for batch in (bulk_events or []))
        self.last_ingestion_result = {
            "received": len(add_events),
            "accepted": accepted,
            "skipped": max(0, len(add_events) - accepted - errored),
            "errored": errored,
        }
        return bulk_events

    @staticmethod
    def generate_external_id(item: str, resource_id: str, resource_name: str, resource_type: str, source_id) -> str:
        components = "|".join(
            [
                str(item or ""),
                str(resource_id or ""),
                str(resource_name or ""),
                str(resource_type or ""),
                str(source_id or ""),
            ]
        )
        return hashlib.md5(components.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_lookup_value(value) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def resolve_recovery_external_id(self, event: Event) -> Optional[str]:
        if event.action not in [EventAction.RECOVERY, EventAction.CLOSED]:
            return None

        item = self._normalize_lookup_value(event.item)
        resource_name = self._normalize_lookup_value(event.resource_name)
        resource_id = self._normalize_lookup_value(event.resource_id)
        resource_type = self._normalize_lookup_value(event.resource_type)

        if not item or not resource_name or resource_id or resource_type:
            return None

        prefetch_qs = Event.objects.filter(
            action=EventAction.CREATED,
            source=self.alert_source,
            item=item,
            resource_name=resource_name,
        ).only("external_id", "item", "resource_name", "source_id", "action")

        candidate_alerts = (
            Alert.objects.filter(
                status__in=AlertStatus.ACTIVATE_STATUS,
                events__source=self.alert_source,
                events__item=item,
                events__resource_name=resource_name,
                events__action=EventAction.CREATED,
            )
            .prefetch_related(Prefetch("events", queryset=prefetch_qs, to_attr="_created_events"))
            .distinct()
        )

        matched_external_ids = []
        for alert in candidate_alerts:
            created_external_ids = {
                existing_event.external_id
                for existing_event in alert._created_events
                if existing_event.external_id
            }
            if len(created_external_ids) == 1:
                matched_external_ids.append(next(iter(created_external_ids)))

        matched_external_ids = list(dict.fromkeys(matched_external_ids))

        if len(matched_external_ids) == 1:
            logger.info(
                "Resolved recovery external_id from active alert: source_id=%s item=%s resource_name=%s",
                self.alert_source.source_id,
                item,
                resource_name,
            )
            return matched_external_ids[0]

        if len(matched_external_ids) > 1:
            logger.warning(
                "Ambiguous recovery external_id candidates, skip compatibility resolution: source_id=%s item=%s resource_name=%s",
                self.alert_source.source_id,
                item,
                resource_name,
            )

        return None

    def _resolve_event_team(self, alert: Dict[str, Any]) -> List:
        """归属组织取值：可信内部推送且 event 自带 organizations 时采信之，否则走 secret 解析结果。

        安全约束：可信内部推送路径下，event 中携带的 organizations 必须是本告警源已注册组织
        （team_secrets.keys()）的子集，超出范围的组织 ID 将被过滤并告警，防止 NATS 内任意
        节点通过伪造 pusher 字符串实现跨组织写污染。
        """
        if self.trusted_internal and "organizations" in alert:
            try:
                requested = normalize_team_ids(alert.get("organizations"))
            except ValueError:
                logger.warning(
                    "[AlertSource] 可信内部推送携带非法 organizations，已置空：source_id=%s organizations=%s",
                    self.alert_source.source_id,
                    alert.get("organizations"),
                )
                return []

            # 仅允许告警源已注册（team_secrets 中存在）的组织，过滤越权组织 ID。
            # 注意：当 team_secrets 为空时，白名单也为空，所有 organizations 均被拒绝（返回 []），
            # 防止未完成注册的告警源被利用绕过跨组织写污染防护。
            authorized_team_ids = {
                str(tid) for tid in (self.alert_source.team_secrets or {}).keys()
            }
            allowed = [tid for tid in requested if str(tid) in authorized_team_ids]
            blocked = [tid for tid in requested if str(tid) not in authorized_team_ids]
            if blocked:
                logger.warning(
                    "[AlertSource] 可信内部推送携带未授权 organizations，已过滤："
                    "source_id=%s blocked=%s allowed=%s",
                    self.alert_source.source_id,
                    blocked,
                    allowed,
                )
            return allowed
        return self.resolved_team

    def add_base_fields(self, event: Event, alert: Dict[str, Any]):
        """添加基础字段"""

        event.source = self.alert_source
        event.push_source_id = (
            alert.get("push_source_id")
            or getattr(event, "push_source_id", None)
            or alert.get("source_id")
            or "default"
        )
        event.raw_data = alert
        event.event_id = f"EVENT-{uuid.uuid4().hex}"
        event.team = self._resolve_event_team(alert)

        if not event.external_id or not str(event.external_id).strip():
            event.external_id = self.resolve_recovery_external_id(event) or self.generate_external_id(
                event.item,
                event.resource_id,
                event.resource_name,
                event.resource_type,
                self.alert_source.source_id,
            )
            logger.debug("[AlertSource] 已生成 external_id for event: %s", event.event_id)

    @staticmethod
    def build_ingress_dedup_key(event: Event) -> Optional[str]:
        """
        构造接入层幂等去重键。

        ingest_key 语义：
        1. event_id 保持“单条数据库记录唯一 ID”；
        2. external_id 保持“业务链路关联键”；
        3. ingest_key 专门作为“接入幂等键”，用于去重与数据库唯一兜底。
        """
        if getattr(event, "ingest_key", None):
            return event.ingest_key

        start_time = getattr(event, "start_time", None)
        if getattr(event, "_start_time_synthesized", False) and start_time is not None:
            # 1-2：源未提供时间、由系统补 now() 时，把用于幂等键的时间截断到分钟，
            # 使同一分钟内的重复推送去重（治无时间戳源的事件表膨胀），
            # 跨分钟的 re-fire 仍因时间不同而能建出新事件。存储的 start_time 不受影响。
            start_time = start_time.replace(second=0, microsecond=0)

        ingest_key = Event.build_ingest_key(
            getattr(event, "source_id", None) or getattr(getattr(event, "source", None), "id", None),
            getattr(event, "push_source_id", None),
            getattr(event, "external_id", None),
            getattr(event, "action", None),
            start_time,
        )
        event.ingest_key = ingest_key
        return ingest_key

    @staticmethod
    def _log_duplicate_event(reason: str, event: Event):
        logger.info(
            "%s: source_id=%s push_source_id=%s external_id=%s action=%s start_time=%s ingest_key=%s",
            reason,
            getattr(event, "source_id", None) or getattr(getattr(event, "source", None), "id", None),
            getattr(event, "push_source_id", None),
            getattr(event, "external_id", None),
            getattr(event, "action", None),
            getattr(event, "start_time", None),
            getattr(event, "ingest_key", None),
        )

    @staticmethod
    def bulk_save_events(events: List[Event]):
        """
        批量保存事件（性能优化版）

        优化点：
        1. 使用 bulk_create 批量入库
        2. 立即查询返回带 pk 的对象（避免后续重复查询）
        3. 保持分批逻辑（每批 100 个）

        Returns:
            List[List[Event]]: 分批后的事件列表（带 pk）
        """
        if not events:
            return []

        # 当前采用 ingest_key 作为接入幂等键：
        # - 应用层先按 ingest_key 批内去重和预查询
        # - 数据库再通过唯一约束兜底，减少并发重复写入
        unique_events = []
        seen_dedup_keys = set()

        for event in events:
            dedup_key = AlertSourceAdapter.build_ingress_dedup_key(event)
            if dedup_key is None:
                unique_events.append(event)
                continue

            if dedup_key in seen_dedup_keys:
                AlertSourceAdapter._log_duplicate_event("Skip duplicated ingress event in current batch", event)
                continue

            seen_dedup_keys.add(dedup_key)
            unique_events.append(event)

        if not unique_events:
            return []

        queryable_ingest_keys = [event.ingest_key for event in unique_events if getattr(event, "ingest_key", None)]
        existing_ingest_keys = set()
        if queryable_ingest_keys:
            source_ids = {
                getattr(event, "source_id", None) or getattr(getattr(event, "source", None), "id", None)
                for event in unique_events
                if getattr(event, "ingest_key", None)
            }
            push_source_ids = {getattr(event, "push_source_id", None) or "default" for event in unique_events if getattr(event, "ingest_key", None)}

            existing_events = Event.objects.filter(
                source_id__in=source_ids,
                push_source_id__in=push_source_ids,
                ingest_key__in=queryable_ingest_keys,
            ).only("ingest_key")

            existing_ingest_keys = {existing_event.ingest_key for existing_event in existing_events if existing_event.ingest_key}

        events_to_create = []
        for event in unique_events:
            ingest_key = getattr(event, "ingest_key", None)
            if ingest_key is not None and ingest_key in existing_ingest_keys:
                AlertSourceAdapter._log_duplicate_event("Skip already persisted ingress event", event)
                continue
            events_to_create.append(event)

        if not events_to_create:
            logger.info("No new events to save after ingress deduplication.")
            return []

        # 1. 分批保存
        bulk_create_events = split_list(events_to_create, 100)
        all_event_ids = []

        for event_batch in bulk_create_events:
            try:
                Event.objects.bulk_create(event_batch, ignore_conflicts=True)
            except IntegrityError:
                # 命中数据库约束（通常是 ingest_key 唯一约束的并发重复写入）。
                # 注意：ignore_conflicts 只忽略唯一冲突，NOT NULL 等约束仍会触发此异常并丢弃整批，
                # 因此上游已确保事件必填字段完整（见 create_events 跳过空事件）。
                logger.warning("Bulk create hit DB constraint (likely ingest_key conflict); treating as idempotent retry.", exc_info=True)
            # 收集所有 event_id 用于后续查询
            all_event_ids.extend([e.event_id for e in event_batch])

        logger.info("[AlertSource] 批量写入 %s 条事件", len(events_to_create))

        # 2. 优化：立即查询返回带 pk 的对象（1 次查询）
        # 避免后续 event_operator 需要用 event_id 再查一遍
        created_events = Event.objects.filter(event_id__in=all_event_ids)

        # 3. 重新分批返回（保持与原来相同的数据结构）
        created_events_list = list(created_events)
        result = split_list(created_events_list, 100)

        logger.debug("[AlertSource] 重新加载 %s 条带 pk 的事件", len(created_events_list))
        return result

    @staticmethod
    def timestamp_to_datetime(timestamp: str) -> datetime:
        """将时间戳转换为datetime对象"""
        # 先转为 naive datetime timestamp 微妙
        try:
            dt = datetime.datetime.fromtimestamp(int(timestamp) / 1000 if len(timestamp) == 13 else int(timestamp))
            # 转为 aware datetime（带时区）
            return timezone.make_aware(dt, timezone.get_current_timezone())
        except Exception as e:
            logger.error("[AlertSource] 时间戳转换失败 timestamp=%s: %s", timestamp, e)
            return timezone.now()

    @staticmethod
    def get_active_shields():
        """
        获取所有活跃的屏蔽策略（优化：一次性查询，全局复用）

        Returns:
            QuerySet 或 None
        """
        try:
            from apps.alerts.models import AlertShield

            shields = AlertShield.objects.filter(is_active=True)
            shield_count = shields.count()
            if shield_count:
                logger.debug("[AlertSource] 加载了 %s 个活跃屏蔽策略", shield_count)
                return shields
            return None
        except Exception as e:
            logger.error("[AlertSource] 查询活跃屏蔽策略失败: %s", e, exc_info=True)
            return None

    def event_operator(self, events_list):
        """
        event的自动屏蔽（性能优化版）

        Args:
            events_list: 事件批次列表
        """

        # 优化：预先查询活跃屏蔽策略，避免每批次重复查询
        active_shields = self.get_active_shields()

        for event_list in events_list:
            try:
                execute_shield_check_for_events([i.event_id for i in event_list], active_shields=active_shields)
            except Exception as err:  # noqa
                logger.error("[AlertSource] 事件屏蔽检查失败", exc_info=True)

    def main(self, events=None):
        """使适配器实例可调用"""
        if not events:
            events = self.events
        bulk_events = self.create_events(events)
        if not bulk_events:
            return getattr(
                self,
                "last_ingestion_result",
                {"received": len(events or []), "accepted": 0, "skipped": len(events or []), "errored": 0},
            )

        # 先执行屏蔽：被屏蔽的事件不应再产出告警，因此屏蔽必须先于即时旁路与聚合，
        # 确保即时旁路按最新屏蔽状态过滤。
        self.event_operator(bulk_events)

        # 即时告警旁路：与下方现有聚合主路径并行。dispatch 自身吞掉全部异常，
        # 永不阻断主流程；未配置 INSTANT 策略时直接 no-op，零开销。
        # dispatch 内部会跳过已被屏蔽（status=SHIELD）的事件（事件级·不建警）。
        try:
            from apps.alerts.aggregation.processor.instant_dispatcher import (
                InstantAlertDispatcher,
            )

            InstantAlertDispatcher.dispatch(bulk_events)
        except Exception:  # noqa
            logger.exception("instant dispatch invocation failed; main pipeline continues")

        self.handle_recovery_events(bulk_events)
        return self.last_ingestion_result

    @staticmethod
    def handle_recovery_events(bulk_events):
        """
        处理恢复事件：将 RECOVERY/CLOSED 事件关联到对应的 Alert

        Args:
            bulk_events: 批量创建的事件列表（分批后的列表）
        """

        for event_batch in bulk_events:
            # 过滤出 RECOVERY 和 CLOSED 类型的事件
            recovery_events = [e for e in event_batch if e.action in [EventAction.RECOVERY, EventAction.CLOSED]]

            if recovery_events:
                try:
                    RecoveryHandler.handle_recovery_events(recovery_events)
                    logger.info("[AlertSource] 处理了 %s 个恢复事件 (RECOVERY/CLOSED)", len(recovery_events))
                except Exception as err:
                    logger.error("[AlertSource] 恢复事件处理失败", exc_info=True)


class AlertSourceAdapterFactory:
    """告警源适配器工厂"""

    _default_adapter_types = ("restful", "nats", "prometheus", "zabbix")
    _adapters = {}

    @classmethod
    def ensure_registered(cls):
        """确保内置告警源适配器已注册。"""
        if all(source_type in cls._adapters for source_type in cls._default_adapter_types):
            return

        from apps.alerts.common.source_adapter.nats import NatsAdapter
        from apps.alerts.common.source_adapter.prometheus import PrometheusAdapter
        from apps.alerts.common.source_adapter.restful import RestFulAdapter
        from apps.alerts.common.source_adapter.zabbix import ZabbixAdapter

        default_adapters = {
            "restful": RestFulAdapter,
            "nats": NatsAdapter,
            "prometheus": PrometheusAdapter,
            "zabbix": ZabbixAdapter,
        }
        for source_type, adapter_class in default_adapters.items():
            cls.register_adapter(source_type, adapter_class)

    @classmethod
    def register_adapter(cls, source_type: str, adapter_class):
        """注册适配器"""
        registered_adapter = cls._adapters.get(source_type)
        if registered_adapter is adapter_class:
            return
        if registered_adapter is not None:
            logger.warning(
                "[AlertSource] 适配器已存在并将被覆盖 source type: %s, old: %s, new: %s",
                source_type,
                registered_adapter,
                adapter_class,
            )
        cls._adapters[source_type] = adapter_class
        logger.info("[AlertSource] 适配器已注册 source type: %s", source_type)

    @classmethod
    def get_adapter(cls, alert_source: AlertSource):
        """获取适配器实例"""
        cls.ensure_registered()
        adapter_class = cls._adapters.get(alert_source.source_type)
        if not adapter_class:
            raise ValueError(f"No adapter found for source type: {alert_source.source_type}")
        return adapter_class

    @classmethod
    def get_supported_types(cls) -> List[str]:
        """获取支持的告警源类型"""
        cls.ensure_registered()
        return list(cls._adapters.keys())
