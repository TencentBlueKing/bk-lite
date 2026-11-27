# -- coding: utf-8 --
"""阿里云 EventBridge 与腾讯云事件总线适配器。

解析无副作用。CMDB 查询失败只留空 cmdb_id，不把整包打成 400。
同一 external_id 已有未关闭告警时，后到的发生挂到那条告警上，不再走即时新建。
"""

from apps.alerts.common.source_adapter.base import INTEGRATION_SECRET_PLACEHOLDER, AlertSourceAdapter
from apps.alerts.common.source_adapter.cloud_catalog import catalog_rows, parse_body
from apps.alerts.common.source_adapter.cloud_guide import callback_origin, cloud_operator_guide, cloud_request_examples, webhook_path
from apps.alerts.constants.constants import AlertStatus, EventAction
from apps.core.logger import alert_logger as logger

_LOOKUP_LIMIT = 5
_UNRECOGNIZED = "Unrecognized cloud event payload."


def _log_token(value, limit=120):
    return str(value or "").replace("\r", " ").replace("\n", " ")[:limit]


def _lookup_cloud_instance_impl(model_id, resource_id, organization_ids):
    """按模型属性 resource_id 在事件所属组织里找实例。

    返回 (inst_uuid 或 None, outcome)。零条、多条或无法证明唯一时不返回 UUID。
    """
    if not model_id or not resource_id or not organization_ids:
        return None, "empty"
    from apps.cmdb.constants.constants import INSTANCE
    from apps.cmdb.graph.drivers.graph_client import GraphClient

    wanted = {str(item) for item in organization_ids if item is not None and str(item) != ""}
    permission = {item: [] for item in organization_ids if item is not None and str(item) != ""}
    with GraphClient() as client:
        result = client.query_entity(
            INSTANCE,
            [
                {"field": "model_id", "type": "str=", "value": model_id},
                {"field": "resource_id", "type": "str=", "value": resource_id},
            ],
            format_permission_dict=permission,
            page={"skip": 0, "limit": _LOOKUP_LIMIT},
            include_count=True,
            fields=["inst_uuid", "organization", "resource_id"],
        )
    if isinstance(result, tuple):
        rows = result[0] or []
        count = result[1] if len(result) > 1 and isinstance(result[1], int) else len(rows)
    else:
        rows = result or []
        count = len(rows)
    matched = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        organization = row.get("organization")
        if isinstance(organization, (list, tuple, set)):
            orgs = {str(item) for item in organization}
        elif organization is None:
            orgs = set()
        else:
            orgs = {str(organization)}
        if wanted.intersection(orgs) and row.get("inst_uuid"):
            matched.append(str(row["inst_uuid"]))
    if count > len(rows):
        return None, "ambiguous"
    if len(matched) == 1:
        return matched[0], "matched"
    if not matched:
        return None, "empty"
    return None, "ambiguous"


lookup_cloud_instance = _lookup_cloud_instance_impl


class CloudResourceEventAdapter(AlertSourceAdapter):
    """两张云事件源共用的接收入口。"""

    vendor = ""
    accepts_query_secret = False

    def __init__(self, alert_source, secret=None, events=None, trusted_internal=False):
        super().__init__(alert_source, secret=secret, events=events, trusted_internal=trusted_internal)
        self.catalog_skipped = 0

    def fetch_alerts(self):
        return []

    def get_integration_guide(self, base_url, language=None, credential=INTEGRATION_SECRET_PLACEHOLDER):
        guide = super().get_integration_guide(base_url, language=language, credential=credential)
        source_id = self.alert_source.source_id
        path = webhook_path(source_id)
        webhook_url = f"{callback_origin(base_url)}{path}"
        guide["webhook_url"] = webhook_url
        guide["headers"] = {"SECRET": credential}
        guide["report_fields"] = catalog_rows(self.vendor)
        guide.update(cloud_operator_guide(self.vendor))
        guide["base_info"] = {
            "id": source_id,
            "url": path,
            "method": "POST",
            "headers": {"SECRET": credential},
            "params": {},
            "content_type": "application/json",
            "description": guide.get("description") or "",
        }
        query_url = None
        if self.accepts_query_secret:
            query_url = f"{webhook_url}?secret={credential}"
            guide["query_secret"] = "secret"
            guide["webhook_url_with_secret"] = query_url
        built = cloud_request_examples(source_id, webhook_url, credential, query_url)
        guide["examples"] = {"CURL": built["CURL"], "Python": built["Python"]}
        guide["example_items"] = built["items"]
        return guide

    def normalize_payload(self, payload):
        bodies = self._bodies(payload)
        parsed_rows = [parse_body(self.vendor, body) for body in bodies]
        if any(row.get("outcome") == "reject" for row in parsed_rows):
            raise ValueError(_UNRECOGNIZED)
        accepted = []
        skipped = 0
        for parsed in parsed_rows:
            event_type = _log_token(parsed.get("event_type"))
            if parsed.get("outcome") == "skip":
                skipped += 1
                logger.warning(
                    "cloud event skipped source_id=%s event_type=%s outcome=%s",
                    self.alert_source.source_id,
                    event_type,
                    "catalog_skip",
                )
                continue
            event = parsed.get("event") or {}
            self._attach_cmdb(event, parsed, event_type)
            accepted.append(event)
            logger.debug(
                "cloud event accepted source_id=%s event_type=%s outcome=%s",
                self.alert_source.source_id,
                event_type,
                "accepted",
            )
        self.catalog_skipped = skipped
        logger.info(
            "cloud event batch source_id=%s received=%s accepted=%s catalog_skipped=%s",
            self.alert_source.source_id,
            len(bodies),
            len(accepted),
            skipped,
        )
        return accepted

    def main(self, events=None):
        if not events:
            events = self.events
        bulk_events = self.create_events(events)
        if not bulk_events:
            return getattr(
                self,
                "last_ingestion_result",
                {"received": len(events or []), "accepted": 0, "skipped": len(events or []), "errored": 0},
            )
        attached = self._attach_open_alerts(bulk_events)
        self.event_operator(bulk_events)
        try:
            from apps.alerts.aggregation.processor.instant_dispatcher import InstantAlertDispatcher

            InstantAlertDispatcher.dispatch(self._without(bulk_events, attached))
        except Exception:
            logger.exception("instant dispatch invocation failed; main pipeline continues")
        self.handle_recovery_events(bulk_events)
        return self.last_ingestion_result

    def _bodies(self, payload):
        if not isinstance(payload, dict):
            raise ValueError(_UNRECOGNIZED)
        batch = payload.get("_batch")
        if isinstance(batch, list) and not any(key in payload for key in ("type", "alarmType", "specversion")):
            return batch
        return [payload]

    def _attach_cmdb(self, event, parsed, event_type):
        model_id = parsed.get("cmdb_model")
        resource_id = parsed.get("cmdb_resource_id")
        if not model_id or not resource_id:
            return
        try:
            inst_uuid, outcome = lookup_cloud_instance(model_id, resource_id, self.resolved_team or [])
        except Exception as exc:
            logger.warning(
                "cloud cmdb lookup failed source_id=%s event_type=%s failed_stage=%s outcome=%s error_type=%s",
                self.alert_source.source_id,
                event_type,
                "cmdb_lookup",
                "cmdb_failed",
                type(exc).__name__,
            )
            return
        if outcome == "matched" and inst_uuid:
            event["cmdb_id"] = inst_uuid
            return
        if outcome == "ambiguous":
            logger.warning(
                "cloud cmdb lookup skipped source_id=%s event_type=%s failed_stage=%s outcome=%s",
                self.alert_source.source_id,
                event_type,
                "cmdb_lookup",
                "cmdb_ambiguous",
            )

    def _attach_open_alerts(self, bulk_events):
        from apps.alerts.aggregation.recovery.match_key import build_recovery_match_key
        from apps.alerts.models.models import Alert

        created = []
        for batch in bulk_events or []:
            for event in batch or []:
                if event.action == EventAction.CREATED and event.external_id:
                    created.append(event)
        if not created:
            return set()
        external_ids = {event.external_id for event in created}
        alerts = (
            Alert.objects.filter(
                status__in=AlertStatus.ACTIVATE_STATUS,
                events__external_id__in=external_ids,
                events__action=EventAction.CREATED,
                events__source=self.alert_source,
            )
            .prefetch_related("events")
            .distinct()
        )
        by_key = {}
        for alert in alerts:
            for linked in alert.events.all():
                if linked.action != EventAction.CREATED:
                    continue
                key = build_recovery_match_key(linked)
                if key:
                    by_key.setdefault(key, alert)
        attached = set()
        for event in created:
            alert = by_key.get(build_recovery_match_key(event))
            if alert is None:
                continue
            try:
                alert.events.add(event)
            except Exception as exc:
                logger.warning(
                    "cloud event attach failed source_id=%s event_type=%s failed_stage=%s outcome=%s error_type=%s",
                    self.alert_source.source_id,
                    _log_token(event.item),
                    "attach_open_alert",
                    "attach_failed",
                    type(exc).__name__,
                )
                continue
            attached.add(event.event_id)
            logger.info(
                "cloud event attached source_id=%s event_type=%s outcome=%s",
                self.alert_source.source_id,
                _log_token(event.item),
                "attach_open_alert",
            )
        return attached

    @staticmethod
    def _without(bulk_events, attached_ids):
        filtered = []
        for batch in bulk_events or []:
            kept = [event for event in batch or [] if event.event_id not in attached_ids]
            if kept:
                filtered.append(kept)
        return filtered


class AliyunEventBridgeAdapter(CloudResourceEventAdapter):
    vendor = "aliyun"


class TencentEventBusAdapter(CloudResourceEventAdapter):
    vendor = "tencent"
    accepts_query_secret = True
