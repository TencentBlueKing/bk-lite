import time
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.apm.adapters import SystemMgmtNotificationDispatcher, VictoriaTracesTelemetryStore
from apps.apm.models import ApmPolicy, ApmSlo
from apps.apm.services import DjangoApmPolicyService, TelemetryCatalogReconciler
from apps.apm.services.contracts import InstanceActivityQuery


namespace = "apm-demo-shop"
environment = "local"
store = VictoriaTracesTelemetryStore()
deadline = time.monotonic() + 90
activities = []
while time.monotonic() < deadline:
    now = timezone.now()
    activities = [
        item
        for item in store.instance_activity(
            InstanceActivityQuery(started_at=now - timedelta(minutes=10), ended_at=now)
        )
        if item.service_namespace == namespace
    ]
    if len({item.service_name for item in activities}) >= 5:
        break
    time.sleep(1)
else:
    raise RuntimeError(f"APM demo telemetry not ready; discovered={activities!r}")

observed_at = timezone.now()
reconciled = TelemetryCatalogReconciler(store).reconcile(
    observed_at=observed_at,
    lookback=timedelta(minutes=10),
)

from apps.apm.models import ApmService  # noqa: E402


services = {
    item.name: item
    for item in ApmService.objects.filter(namespace=namespace, archived_at__isnull=True)
}
storefront = services["demo-storefront"]

slo_specs = (
    (
        "商品列表可用性",
        {
            "service": storefront,
            "environment": environment,
            # 全服务 7 天窗口在本地 demo 遥测量下会触发 VT 查询上限；按 endpoint 收敛口径。
            "endpoint": "GET /api/products",
            "sli_type": ApmSlo.SliType.AVAILABILITY,
            "objective": Decimal("99.900"),
            "latency_threshold_ms": None,
            "evaluation_window": ApmSlo.EvaluationWindow.ROLLING_7D,
            "is_enabled": True,
            "updated_by": "apm-demo",
        },
    ),
    (
        "结算接口 500ms 时延目标",
        {
            "service": storefront,
            "environment": environment,
            "endpoint": "POST /api/checkout",
            "sli_type": ApmSlo.SliType.LATENCY_P95,
            "objective": Decimal("95.000"),
            "latency_threshold_ms": 500,
            "evaluation_window": ApmSlo.EvaluationWindow.ROLLING_7D,
            "is_enabled": True,
            "updated_by": "apm-demo",
        },
    ),
)
for name, defaults in slo_specs:
    ApmSlo.objects.update_or_create(
        name=name,
        service=storefront,
        environment=environment,
        defaults=defaults,
    )

policy_specs = (
    (
        "演示商城错误率过高",
        ApmPolicy.MetricType.ERROR_RATE,
        ApmPolicy.Comparator.GREATER_THAN,
        Decimal("0.010000"),
        ApmPolicy.Severity.CRITICAL,
    ),
    (
        "演示商城 P95 过慢",
        ApmPolicy.MetricType.P95,
        ApmPolicy.Comparator.GREATER_THAN,
        Decimal("100.000000"),
        ApmPolicy.Severity.WARNING,
    ),
)
policy_service = DjangoApmPolicyService(store, SystemMgmtNotificationDispatcher())
evaluation_results = []
for name, metric_type, comparator, threshold, severity in policy_specs:
    policy, _ = ApmPolicy.objects.update_or_create(
        name=name,
        service=storefront,
        environment=environment,
        defaults={
            "metric_type": metric_type,
            "comparator": comparator,
            "threshold": threshold,
            "duration_window": 1,
            "recovery_window": 1,
            "severity": severity,
            "notice": False,
            "notice_type_ids": [],
            "notice_users": [],
            "is_enabled": True,
            "updated_by": "apm-demo",
        },
    )
    policy_service.save_policy(policy)
    result = policy_service.test_query(policy, evaluated_at=timezone.now())
    policy_service.evaluate(policy.id, evaluated_at=timezone.now())
    evaluation_results.append(
        {
            "policy": name,
            "value": str(result.value) if result.value is not None else None,
            "breached": result.breached,
        }
    )

print(
    {
        "reconciled": reconciled,
        "services": sorted(services),
        "slos": len(slo_specs),
        "policies": evaluation_results,
    }
)
