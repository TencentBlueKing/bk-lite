from datetime import datetime, timedelta

from apps.apm.services.catalog import DjangoTelemetryCatalogService
from apps.apm.services.contracts import (
    CatalogDiscovery,
    CatalogReconcileResult,
    InstanceActivityQuery,
    MetricStore,
)


class TelemetryCatalogReconciler:
    """把遥测活动折叠为目录元数据；外部查询与 ORM 状态机止于此接口。"""

    def __init__(self, metric_store: MetricStore, catalog: DjangoTelemetryCatalogService | None = None):
        self.metric_store = metric_store
        self.catalog = catalog or DjangoTelemetryCatalogService()

    def reconcile(self, *, observed_at: datetime, lookback: timedelta = timedelta(minutes=20)) -> CatalogReconcileResult:
        activities = self.metric_store.instance_activity(
            InstanceActivityQuery(started_at=observed_at - lookback, ended_at=observed_at)
        )
        service_ids = set()
        instance_ids = set()
        missing_identities = 0
        for activity in activities:
            result = self.catalog.discover(
                CatalogDiscovery(
                    ingest_source_id=activity.ingest_source_id,
                    service_namespace=activity.service_namespace,
                    service_name=activity.service_name,
                    instance_id=activity.instance_id,
                    environment=activity.environment,
                    version=activity.version,
                    seen_at=activity.last_seen_at,
                )
            )
            if result.missing_instance_identity:
                missing_identities += 1
                continue
            service_ids.add(result.service.id)
            instance_ids.add(result.instance.id)

        archived_services, archived_instances = self.catalog.archive_stale(observed_at=observed_at)
        return CatalogReconcileResult(
            discovered_services=len(service_ids),
            discovered_instances=len(instance_ids),
            missing_instance_identities=missing_identities,
            archived_services=archived_services,
            archived_instances=archived_instances,
        )
