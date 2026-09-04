"""指标目录 keyword 过滤：同时匹配指标 ID 与当前 UI 语言的展示名。

列表接口在序列化阶段用 LanguageLoader 把 `display_name` 覆盖为
`monitor_object_metric.<Object>.<metric>.name`（见 MetricViewSet.list）。
DB 的 display_name 多为英文模板名，按库字段 icontains 搜「内存」会空结果。
此处按账号 locale 扫描同一份语言包，把命中的指标 ID 并入过滤条件。
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


def get_locale_metric_names_matching_keyword(keyword: str, locale: str) -> set[str]:
    """返回当前 locale 展示名（或 IF-MIB 文案）包含 keyword 的指标 ID。"""
    needle = str(keyword or "").strip().casefold()
    if not needle:
        return set()

    names = set(get_ifmib_metric_names_matching_keyword(keyword, locale))
    lan = LanguageLoader(app=LanguageConstants.APP, default_lang=locale_for_metric_language(locale))
    metrics_root = lan.get(LanguageConstants.MONITOR_OBJECT_METRIC)
    if not isinstance(metrics_root, dict):
        return names

    for object_metrics in metrics_root.values():
        if not isinstance(object_metrics, dict):
            continue
        for metric_name, entry in object_metrics.items():
            display = entry.get("name") if isinstance(entry, dict) else entry
            if needle in str(display or "").casefold():
                names.add(str(metric_name))
    return names


def apply_metric_keyword_filter(queryset, keyword, locale=""):
    """按 keyword 过滤指标：ID / DB 展示名 / 描述 / 当前语言包展示名。"""
    keyword = str(keyword or "").strip()
    if not keyword:
        return queryset
    localized_names = get_locale_metric_names_matching_keyword(keyword, locale)
    return queryset.filter(
        Q(name__icontains=keyword) | Q(display_name__icontains=keyword) | Q(description__icontains=keyword) | Q(name__in=localized_names)
    )
