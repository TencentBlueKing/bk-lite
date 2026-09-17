from datetime import datetime, timedelta

from apps.apm.models import ApmApplication
from apps.apm.services.catalog import DjangoTelemetryCatalogService, InvalidCatalogIdentity
from apps.apm.services.contracts import CatalogDiscovery, CatalogReconcileResult, InstanceActivity, InstanceActivityQuery, MetricStore
from apps.apm.services.deployments import DeploymentEventRecorder, ObservedVersion
from apps.apm.services.identity import normalize_identity
from apps.core.logger import apm_logger as logger

MAX_UNKNOWN_APPLICATION_SAMPLES = 20
MAX_INVALID_IDENTITY_SAMPLES = 20
DISCOVER_BATCH_SIZE = 500


def _activity_identity(activity: InstanceActivity) -> tuple[str, str, str]:
    return (
        normalize_identity(activity.service_namespace),
        normalize_identity(activity.service_name),
        normalize_identity(activity.instance_id),
    )


def _dedupe_activities(activities: list[InstanceActivity]) -> list[CatalogDiscovery]:
    latest: dict[tuple[str, str, str], CatalogDiscovery] = {}
    order: list[tuple[str, str, str]] = []
    for activity in activities:
        key = _activity_identity(activity)
        discovery = CatalogDiscovery(
            service_namespace=activity.service_namespace,
            service_name=activity.service_name,
            instance_id=activity.instance_id,
            environment=activity.environment,
            version=activity.version,
            language=activity.language,
            seen_at=activity.last_seen_at,
        )
        previous = latest.get(key)
        if previous is None:
            order.append(key)
            latest[key] = discovery
            continue
        if activity.last_seen_at >= (previous.seen_at or activity.last_seen_at):
            latest[key] = discovery
    return [latest[key] for key in order]


class TelemetryCatalogReconciler:
    """把遥测活动折叠为目录元数据；外部查询与 ORM 状态机止于此接口。"""

    def __init__(
        self,
        metric_store: MetricStore,
        catalog: DjangoTelemetryCatalogService | None = None,
        deployments: DeploymentEventRecorder | None = None,
    ):
        self.metric_store = metric_store
        self.catalog = catalog or DjangoTelemetryCatalogService()
        self.deployments = deployments or DeploymentEventRecorder()

    def reconcile(self, *, observed_at: datetime, lookback: timedelta = timedelta(minutes=20)) -> CatalogReconcileResult:
        activities = self.metric_store.instance_activity(InstanceActivityQuery(started_at=observed_at - lookback, ended_at=observed_at))
        service_ids = set()
        instance_ids = set()
        missing_identities = 0
        unknown_applications = set()
        invalid_activities = 0
        invalid_identity_samples: list[dict] = []
        observations: list[ObservedVersion] = []
        discoveries = _dedupe_activities(activities)
        for start in range(0, len(discoveries), DISCOVER_BATCH_SIZE):
            batch = discoveries[start : start + DISCOVER_BATCH_SIZE]
            for discovery, outcome in zip(batch, self.catalog.discover_many(batch), strict=True):
                if isinstance(outcome, ApmApplication.DoesNotExist):
                    unknown_applications.add(discovery.service_namespace)
                    continue
                if isinstance(outcome, InvalidCatalogIdentity):
                    invalid_activities += 1
                    if len(invalid_identity_samples) < MAX_INVALID_IDENTITY_SAMPLES:
                        invalid_identity_samples.append(
                            {
                                "field": outcome.field,
                                "reason": outcome.reason,
                                "length": outcome.length,
                                "limit": outcome.limit,
                            }
                        )
                    continue
                if isinstance(outcome, BaseException):
                    raise outcome
                if outcome.service is not None:
                    service_ids.add(outcome.service.id)
                    version = normalize_identity(discovery.version)
                    if version:
                        observations.append(
                            ObservedVersion(
                                service=outcome.service,
                                environment=discovery.environment,
                                version=version,
                                last_seen_at=discovery.seen_at,
                            )
                        )
                if outcome.missing_instance_identity:
                    missing_identities += 1
                    continue
                instance_ids.add(outcome.instance.id)

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
        try:
            recorded = self.deployments.record(observations, observed_at=observed_at)
        except Exception:
            logger.exception("APM deployment event record failed")
            raise
        return CatalogReconcileResult(
            discovered_services=len(service_ids),
            discovered_instances=len(instance_ids),
            missing_instance_identities=missing_identities,
            archived_services=0,
            unknown_applications=len(unknown_applications),
            invalid_activities=invalid_activities,
            deployment_events_created=recorded.created,
            deployment_events_updated=recorded.updated,
            deployment_events_pruned=recorded.pruned,
        )
