"""指标目录 keyword 过滤：同时匹配指标 ID 与当前 UI 语言的展示名。

列表接口在序列化阶段用 LanguageLoader 把 `display_name` 覆盖为
`monitor_object_metric.<Object>.<metric>.name`（见 MetricViewSet.list）。
DB 的 display_name 多为英文模板名，按库字段 icontains 搜「内存」会空结果。
此处按账号 locale 扫描同一份语言包，把命中的指标 ID 并入过滤条件。

语言包键按监控对象隔离；同一 metric ID 在不同对象上的展示名可能不同。
反查必须限定到 queryset 内的对象，避免跨对象文案误命中裸 name__in。
"""

from django.db.models import Q

from apps.core.utils.loader import LanguageLoader
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.utils.snmp_ifmib_capability import get_ifmib_metric_names_matching_keyword


def locale_for_metric_language(locale: str) -> str:
    """LanguageLoader 只认 en / zh-Hans 文件名。"""
    raw = str(locale or "").strip()
    lowered = raw.lower().replace("_", "-")
    if lowered.startswith("zh"):
        return "zh-Hans"
    if lowered.startswith("en"):
        return "en"
    return raw or "en"


def get_locale_metric_names_matching_keyword(
    keyword: str,
    locale: str,
    object_names: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict[str, set[str]]:
    """返回 {监控对象名: 展示名包含 keyword 的指标 ID 集合}。

    ``object_names`` 为空时不扫描语言包（只保留调用方另行合并的 IF-MIB 等闭集），
    避免无对象上下文时跨对象误命中。
    """
    needle = str(keyword or "").strip().casefold()
    scoped = {str(name) for name in (object_names or []) if str(name or "").strip()}
    if not needle or not scoped:
        return {}

    lan = LanguageLoader(app=LanguageConstants.APP, default_lang=locale_for_metric_language(locale))
    metrics_root = lan.get(LanguageConstants.MONITOR_OBJECT_METRIC)
    if not isinstance(metrics_root, dict):
        return {}

    matched: dict[str, set[str]] = {}
    for object_name in scoped:
        object_metrics = metrics_root.get(object_name)
        if not isinstance(object_metrics, dict):
            continue
        hits: set[str] = set()
        for metric_name, entry in object_metrics.items():
            display = entry.get("name") if isinstance(entry, dict) else entry
            if needle in str(display or "").casefold():
                hits.add(str(metric_name))
        if hits:
            matched[object_name] = hits
    return matched


def apply_metric_keyword_filter(queryset, keyword, locale=""):
    """按 keyword 过滤指标：ID / DB 展示名 / 描述 / 当前对象语言包展示名。"""
    keyword = str(keyword or "").strip()
    if not keyword:
        return queryset

    object_names = [name for name in queryset.order_by().values_list("monitor_object__name", flat=True).distinct() if name]
    localized_by_object = get_locale_metric_names_matching_keyword(keyword, locale, object_names)
    ifmib_names = get_ifmib_metric_names_matching_keyword(keyword, locale)

    condition = Q(name__icontains=keyword) | Q(display_name__icontains=keyword) | Q(description__icontains=keyword)
    if ifmib_names:
        condition |= Q(name__in=ifmib_names)
    for object_name, metric_names in localized_by_object.items():
        condition |= Q(monitor_object__name=object_name, name__in=metric_names)
    return queryset.filter(condition)
