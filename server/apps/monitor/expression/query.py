from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.expression.compiler import CompiledFormula, FormulaCompiler
from apps.monitor.models.monitor_metrics import Metric
from apps.monitor.tasks.utils.metric_query import format_to_vm_filter


def build_metric_query(metric, filters: list[dict]) -> str:
    vm_filter = format_to_vm_filter(filters or [])
    return (metric.query or "").replace("__$labels__", vm_filter)


def build_formula_query(query_condition: dict) -> CompiledFormula:
    metric_ids = [item["metric_id"] for item in query_condition.get("queries") or []]
    metrics = Metric.objects.filter(id__in=metric_ids)
    by_id = {metric.id: metric for metric in metrics}
    missing = [metric_id for metric_id in metric_ids if metric_id not in by_id]
    if missing:
        raise BaseAppException(f"metric does not exist [{missing[0]}]")
    return FormulaCompiler(query_condition, by_id).compile()
