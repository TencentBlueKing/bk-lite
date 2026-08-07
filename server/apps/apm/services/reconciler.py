import logging
from datetime import datetime, timedelta

from apps.apm.models import ApmApplication
from apps.apm.services.catalog import DjangoTelemetryCatalogService, InvalidCatalogIdentity
from apps.apm.services.contracts import CatalogDiscovery, CatalogReconcileResult, InstanceActivityQuery, MetricStore

logger = logging.getLogger(__name__)
MAX_UNKNOWN_APPLICATION_SAMPLES = 20
MAX_INVALID_IDENTITY_SAMPLES = 20


class TelemetryCatalogReconciler:
    """把遥测活动折叠为目录元数据；外部查询与 ORM 状态机止于此接口。"""

    def __init__(self, metric_store: MetricStore, catalog: DjangoTelemetryCatalogService | None = None):
        self.metric_store = metric_store
        self.catalog = catalog or DjangoTelemetryCatalogService()

    def reconcile(self, *, observed_at: datetime, lookback: timedelta = timedelta(minutes=20)) -> CatalogReconcileResult:
        activities = self.metric_store.instance_activity(InstanceActivityQuery(started_at=observed_at - lookback, ended_at=observed_at))
        service_ids = set()
        instance_ids = set()
        missing_identities = 0
        unknown_applications = set()
        invalid_activities = 0
        invalid_identity_samples: list[dict] = []
        for activity in activities:
            try:
                result = self.catalog.discover(
                    CatalogDiscovery(
                        service_namespace=activity.service_namespace,
                        service_name=activity.service_name,
                        instance_id=activity.instance_id,
                        environment=activity.environment,
                        version=activity.version,
                        seen_at=activity.last_seen_at,
                    )
                )
            except ApmApplication.DoesNotExist:
                unknown_applications.add(activity.service_namespace)
                continue
            except InvalidCatalogIdentity as exc:
                invalid_activities += 1
                if len(invalid_identity_samples) < MAX_INVALID_IDENTITY_SAMPLES:
                    invalid_identity_samples.append(
                        {
                            "field": exc.field,
                            "reason": exc.reason,
                            "length": exc.length,
                            "limit": exc.limit,
                        }
                    )
                continue
            if result.service is not None:
                service_ids.add(result.service.id)
            if result.missing_instance_identity:
                missing_identities += 1
                continue
            instance_ids.add(result.instance.id)

        archived_services, archived_instances = self.catalog.archive_stale(observed_at=observed_at)
        if unknown_applications:
            logger.warning(
                "APM telemetry ignored unknown applications",
                extra={
                    "unknown_application_count": len(unknown_applications),
                    "unknown_application_samples": sorted(unknown_applications)[:MAX_UNKNOWN_APPLICATION_SAMPLES],
                },
            )
        if invalid_activities:
            logger.warning(
                "APM telemetry ignored invalid catalog identities",
                extra={
                    "invalid_identity_count": invalid_activities,
                    "invalid_identity_samples": invalid_identity_samples,
                },
            )
        return CatalogReconcileResult(
            discovered_services=len(service_ids),
            discovered_instances=len(instance_ids),
            missing_instance_identities=missing_identities,
            archived_services=archived_services,
            archived_instances=archived_instances,
            unknown_applications=len(unknown_applications),
            invalid_activities=invalid_activities,
        )
