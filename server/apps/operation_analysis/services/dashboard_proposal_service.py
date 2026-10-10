"""运营分析仪表盘方案的检索摘要与确定性校验。"""

from __future__ import annotations

import json
import re
from pathlib import Path

_CAPABILITY_PATH = Path(__file__).with_name("dashboard_widget_capabilities.json")


def load_widget_capabilities() -> dict:
    with _CAPABILITY_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("dashboard widget capabilities must be an object")
    return payload


AI_CHART_TYPES = frozenset(item["type"] for item in load_widget_capabilities().get("widgets") or [] if isinstance(item, dict) and item.get("type"))
SCENE_CHART_TYPES = frozenset({"networkStatusTopology", "relatedTopology", "application3D", "room3D"})

SCHEMA_VERSION = "1.0"

_DOMAIN_ALIASES = {
    "cmdb": ("cmdb", "资产"),
    "告警": ("告警", "alarm", "alert", "alerts"),
    "日志": ("日志", "log", "logs"),
    "监控": ("监控", "monitor", "monitoring"),
}
_GENERIC_QUERY_TOKENS = frozenset(
    {
        "帮我",
        "搭建",
        "创建",
        "新建",
        "一个",
        "情况",
        "概览",
        "总览",
        "预览",
        "数据",
        "仪表",
        "表盘",
        "看板",
        "大屏",
        "展示",
        "查看",
        "统计",
        "分析",
        "总数",
        "数量",
        "总量",
    }
)
_OVERVIEW_TERMS = ("概览", "总览", "概况", "整体", "overview", "summary")
_ANALYSIS_SUBJECT_RE = re.compile(r"(?P<subject>[一-鿿A-Za-z0-9_]{1,24}?)(?:分布|占比|比例|构成)$")


def _field_name(item: dict) -> str:
    return str(item.get("key") or item.get("name") or "").strip()


def _fields(source: dict) -> list[dict]:
    schema = source.get("field_schema") or []
    fields = []
    for item in schema:
        if not isinstance(item, dict):
            continue
        name = _field_name(item)
        if not name:
            continue
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or item.get("desc") or "").strip()
        field = {
            "name": name,
            "type": item.get("value_type") or item.get("type") or "",
            "desc": description or title,
        }
        if title:
            field["title"] = title
        fields.append(field)
    return fields


def _public_input_config(param: dict) -> dict | None:
    config = param.get("inputConfig")
    if not isinstance(config, dict) or not config.get("control"):
        return None
    public = {"control": config.get("control")}
    if "multiple" in config:
        public["multiple"] = bool(config.get("multiple"))
    source = config.get("optionsSource")
    if isinstance(source, dict) and source.get("type"):
        public["optionsSource"] = {
            key: source.get(key) for key in ("type", "sourceId", "sourceRef", "valueField", "labelField", "staticItems") if key in source
        }
    return public


def _params(source: dict) -> list[dict]:
    params = source.get("params") or []
    summarized = []
    for item in params:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        summarized.append({**item, "inputConfig": _public_input_config(item)})
    return summarized


def brief_from_source(source: dict) -> dict | None:
    """声明不足的数据源不进入推荐。选项数据源可以没有图表类型。"""
    fields = _fields(source)
    chart_types = [item for item in (source.get("chart_type") or []) if item in AI_CHART_TYPES]
    field_names = {item["name"] for item in fields}
    option_ready = len(field_names) >= 2
    if not chart_types and not option_ready:
        return None
    if chart_types and not fields and not set(chart_types) & {"line", "bar"}:
        return None
    return {
        "id": source.get("id"),
        "name": source.get("name") or "",
        "desc": source.get("desc") or "",
        "tags": source.get("tags") or [],
        "chart_type": chart_types,
        "params": [
            {
                "name": item.get("name"),
                "alias_name": item.get("alias_name") or item.get("name"),
                "type": item.get("type") or "string",
                "filterType": item.get("filterType") or "params",
                "required": bool(item.get("required")),
                "default": item.get("value", item.get("default")),
                **({"inputConfig": item.get("inputConfig")} if item.get("inputConfig") else {}),
            }
            for item in _params(source)
        ],
        "fields": fields,
        "option_ready": option_ready,
    }


def _tokens(text: str) -> set[str]:
    folded = str(text or "").lower()
    parts: list[str] = []
    for token in folded.replace("，", " ").replace(",", " ").replace("、", " ").split():
        if not token:
            continue
        parts.append(token)
        cjk = "".join(char for char in token if "\u4e00" <= char <= "\u9fff")
        if len(cjk) >= 2:
            parts.extend(cjk[index : index + 2] for index in range(len(cjk) - 1))
        latin = []
        buffer: list[str] = []
        for char in token:
            if char.isascii() and char.isalnum():
                buffer.append(char)
                continue
            if buffer:
                latin.append("".join(buffer))
                buffer = []
        if buffer:
            latin.append("".join(buffer))
        parts.extend(latin)
    return {part for part in parts if part}


def _contains_term(text: str, term: str) -> bool:
    folded = str(text or "").casefold()
    value = str(term or "").casefold().strip()
    if not value:
        return False
    if value.isascii():
        return bool(re.search(rf"(?<![a-z0-9_]){re.escape(value)}(?![a-z0-9_])", folded))
    return value in folded


def _canonical_tag(tag: object) -> str:
    return str(tag or "").casefold().strip()


def _domain_terms(tag: str) -> set[str]:
    canonical = _canonical_tag(tag)
    return {canonical, *(_DOMAIN_ALIASES.get(canonical) or ())}


def _requested_domains(requirement: dict, briefs: list[dict]) -> set[str]:
    """Resolve the requested semantic domain from catalog tags, not datasource names.

    A model-proposed domain is only used when the user's requirement text does not
    itself identify a catalog domain. This keeps the LLM at the intent seam while
    the datasource catalog remains authoritative.
    """
    query = " ".join(str(requirement.get(key) or "") for key in ("text", "description", "metric", "dimension"))
    catalog_tags = {
        canonical for brief in briefs if isinstance(brief, dict) for tag in (brief.get("tags") or []) if (canonical := _canonical_tag(tag))
    }
    inferred = {tag for tag in catalog_tags if any(_contains_term(query, term) for term in _domain_terms(tag))}
    if inferred:
        return inferred
    proposed = requirement.get("domain")
    values = proposed if isinstance(proposed, list) else [proposed]
    return {tag for tag in catalog_tags if any(_canonical_tag(value) in _domain_terms(tag) for value in values if value)}


def _is_overview(requirement: dict) -> bool:
    if str(requirement.get("analysisType") or "").casefold() == "overview":
        return True
    text = " ".join(str(requirement.get(key) or "") for key in ("text", "description"))
    return any(_contains_term(text, term) for term in _OVERVIEW_TERMS)


def _brief_search_text(brief: dict) -> tuple[str, str, str, str]:
    name = str(brief.get("name") or "").casefold()
    tags = " ".join(_canonical_tag(item) for item in (brief.get("tags") or []))
    field_names = " ".join(
        f"{item.get('name') or ''} {item.get('title') or ''} {item.get('desc') or ''}"
        for item in (brief.get("fields") or [])
        if isinstance(item, dict)
    ).casefold()
    body = " ".join(
        [
            str(brief.get("desc") or ""),
            " ".join(f"{item.get('alias_name') or ''} {item.get('desc') or ''}" for item in (brief.get("params") or []) if isinstance(item, dict)),
            " ".join(str(item) for item in (brief.get("chart_type") or [])),
        ]
    ).casefold()
    return name, tags, field_names, body


def _requested_subject_tokens(requirement: dict, requested_domains: set[str]) -> set[str]:
    """只对用户明说的分析维度做强校验。

    领域标签只能证明「是告警数据」，不能证明「告警类型」可以用
    「告警状态」替代。宽泛的领域请求没有维度时仍允许领域召回。
    """
    explicit = " ".join(str(requirement.get(key) or "") for key in ("dimension", "metric")).strip()
    text = str(requirement.get("text") or requirement.get("description") or "").strip()
    matched = _ANALYSIS_SUBJECT_RE.search(text)
    if str(requirement.get("analysisType") or "").casefold() != "distribution" and not matched:
        return set()
    subject = explicit or (matched.group("subject") if matched else "")
    if not subject:
        return set()
    for domain in requested_domains:
        for term in sorted(_domain_terms(domain), key=len, reverse=True):
            subject = re.sub(re.escape(term), "", subject, flags=re.I)
    subject = re.sub(r"^(?:当前|活跃|全部|按)", "", subject).strip()
    return _tokens(subject)


def _chart_family(chart_types) -> str:
    types = set(chart_types or [])
    if types & {"line", "bar", "area"}:
        return "trend"
    if "pie" in types:
        return "share"
    if "multiValue" in types:
        return "multi"
    if types & {"table", "topN"}:
        return "table"
    if "gauge" in types:
        return "gauge"
    return "single"


def _prefer_chart_families(ranked: list[tuple], limit: int) -> list[dict]:
    """概览先保留最相关的源，再补上趋势、占比、表格，避免目录里只剩单值。"""
    remaining = list(ranked)
    picked: list[dict] = []
    families: set[str] = set()
    while remaining and len(picked) < limit:
        choice = 0
        if len(picked) >= 2:
            missing = {"trend", "share", "table"} - families
            if missing:
                for index, (_, brief) in enumerate(remaining):
                    if _chart_family(brief.get("chart_type")) in missing:
                        choice = index
                        break
        _, brief = remaining.pop(choice)
        families.add(_chart_family(brief.get("chart_type")))
        picked.append(brief)
    return picked


def search_briefs(requirements: list[dict], briefs: list[dict], *, limit_per_requirement: int = 5, total_limit: int = 20) -> list[dict]:
    """按语义领域和数据契约检索 brief。指定图表时每项最多 5 个，概览会补齐不同图表。"""
    chosen: list[dict] = []
    seen: set[int] = set()
    for requirement in requirements:
        purpose = requirement.get("purpose") or "visualization"
        query = " ".join(str(requirement.get(key) or "") for key in ("text", "chartType", "description", "metric", "dimension"))
        needles = {item for item in _tokens(query) if item not in _GENERIC_QUERY_TOKENS}
        requested_domains = _requested_domains(requirement, briefs) if purpose == "visualization" else set()
        subject_tokens = _requested_subject_tokens(requirement, requested_domains) if purpose == "visualization" else set()
        chart_type = str(requirement.get("chartType") or "")
        overview = _is_overview(requirement)
        ranked = []
        for brief in briefs:
            if purpose == "visualization" and not brief.get("chart_type"):
                continue
            if purpose == "parameter_options" and not brief.get("option_ready"):
                continue
            if chart_type and chart_type not in (brief.get("chart_type") or []):
                continue
            brief_domains = {_canonical_tag(item) for item in (brief.get("tags") or []) if _canonical_tag(item)}
            domain_matches = requested_domains & brief_domains
            if requested_domains and not domain_matches:
                continue
            name, tags, field_names, body = _brief_search_text(brief)
            if subject_tokens and not any(token in name or token in tags or token in field_names or token in body for token in subject_tokens):
                continue
            evidence_score = 24 * len(domain_matches)
            for needle in needles:
                if not needle:
                    continue
                if needle in name:
                    evidence_score += 4
                elif needle in tags or needle in field_names:
                    evidence_score += 2
                elif needle in body:
                    evidence_score += 1
            if evidence_score <= 0:
                continue
            score = evidence_score
            if chart_type:
                score += 3
            if overview:
                if any(_contains_term(name, term) for term in _OVERVIEW_TERMS):
                    score += 12
                number_fields = sum(
                    1
                    for field in (brief.get("fields") or [])
                    if isinstance(field, dict) and str(field.get("type") or "").casefold() in {"number", "integer", "float", "int", "double"}
                )
                score += min(number_fields, 6)
            ranked.append((score, brief))
        ranked.sort(key=lambda item: (-item[0], item[1].get("id") or 0))
        if overview and not chart_type:
            picked = _prefer_chart_families(ranked, min(8, max(limit_per_requirement, 8)))
        else:
            picked = [brief for _, brief in ranked[:limit_per_requirement]]
        for brief in picked:
            source_id = brief.get("id")
            if source_id in seen:
                continue
            seen.add(source_id)
            chosen.append(brief)
            if len(chosen) >= total_limit:
                return chosen
    return chosen


def _widget_fields(config: dict) -> set[str]:
    names = set()
    for key in (
        "selectedFields",
        "descriptionField",
        "dimensionField",
        "valueField",
        "topNLabelField",
        "topNValueField",
        "multiValueLabelField",
        "multiValueValueField",
        "nodeGraphSourceField",
        "nodeGraphTargetField",
        "nodeGraphValueField",
    ):
        value = config.get(key)
        if isinstance(value, list):
            names.update(str(item) for item in value if item)
        elif value:
            names.add(str(value))
    for column in (config.get("tableConfig") or {}).get("columns") or []:
        if isinstance(column, dict) and column.get("key"):
            names.add(str(column["key"]))
    return names


def _param_labels(declared: dict) -> set[str]:
    return {label for label in (declared.get("alias_name"), declared.get("name")) if isinstance(label, str) and label}


def _clear_label_used_as_value(current: dict, declared: dict) -> None:
    """参数中文名不是可查询的值。动态选项没加载时，模型常把「主机」写进 instance_ids。"""
    value = current.get("value")
    labels = _param_labels(declared)
    if not labels or value in (None, ""):
        return
    default = declared.get("default")
    if isinstance(value, list):
        kept = [item for item in value if item not in labels or item == default]
        if len(kept) != len(value):
            current["value"] = kept
        return
    if isinstance(value, str) and value in labels and default != value:
        current["value"] = None


def _normalize_table_columns(config: dict) -> None:
    table = config.get("tableConfig")
    if not isinstance(table, dict):
        return
    columns = table.get("columns")
    if not isinstance(columns, list):
        return
    normalized = []
    for index, column in enumerate(columns):
        if not isinstance(column, dict) or not column.get("key"):
            continue
        normalized.append(
            {
                **column,
                "title": column.get("title") or column["key"],
                "visible": True if column.get("visible") is None else column.get("visible"),
                "order": index if column.get("order") is None else column.get("order"),
            }
        )
    config["tableConfig"] = {**table, "columns": normalized}


def _brief_by_id(by_id: dict, source_id):
    if source_id in by_id:
        return by_id[source_id]
    text = str(source_id)
    for key, brief in by_id.items():
        if str(key) == text:
            return brief
    return None


def _dynamic_source_error(input_config, by_id: dict) -> str | None:
    if not isinstance(input_config, dict):
        return None
    source = input_config.get("optionsSource") or {}
    if not isinstance(source, dict) or source.get("type") != "dynamic":
        return None
    source_ref = source.get("sourceRef")
    if isinstance(source_ref, dict) and source_ref.get("type") and source_ref.get("value"):
        return None
    brief = _brief_by_id(by_id, source.get("sourceId"))
    if brief is None or not brief.get("option_ready"):
        return "options_source"
    names = {field["name"] for field in brief.get("fields") or []}
    if source.get("valueField") not in names or source.get("labelField") not in names:
        return "options_field"
    return None


def _brief_field_names(brief: dict) -> list[str]:
    return [str(field["name"]) for field in (brief.get("fields") or []) if isinstance(field, dict) and field.get("name")]


def _compact_source_index(briefs: list[dict], *, budget: int = 900) -> list[dict]:
    """失败时给模型的目录。优先保住 id，超长时从尾部去掉字段。"""
    entries = []
    for brief in briefs or []:
        if not isinstance(brief, dict) or brief.get("id") is None or not brief.get("chart_type"):
            continue
        entries.append(
            {
                "id": brief.get("id"),
                "name": brief.get("name") or "",
                "chart_type": list(brief.get("chart_type") or []),
                "fields": _brief_field_names(brief),
            }
        )

    def encoded() -> str:
        return json.dumps(entries, ensure_ascii=False, separators=(",", ":"))

    for entry in reversed(entries):
        if len(encoded()) <= budget:
            return entries
        entry["fields"] = []
    while entries and len(encoded()) > budget:
        entries.pop()
    return entries


def _first_present(source: dict, keys: tuple[str, ...]):
    for key in keys:
        value = source.get(key)
        if value not in (None, "", []):
            return value
    return None


def _coerce_widget_item(item: dict) -> dict:
    """模型常把图表配置写在组件根上，收进 valueConfig 后再校验。"""
    config = dict(item.get("valueConfig") or {}) if isinstance(item.get("valueConfig"), dict) else {}
    aliases = {
        "chartType": ("chartType", "chart_type"),
        "dataSource": ("dataSource", "dataSourceId", "data_source_id", "data_source"),
        "selectedFields": ("selectedFields", "selected_fields"),
        "dimensionField": ("dimensionField", "dimension_field"),
        "valueField": ("valueField", "value_field"),
        "dataSourceParams": ("dataSourceParams", "data_source_params"),
    }
    for key, names in aliases.items():
        if config.get(key) not in (None, "", []):
            continue
        found = _first_present(item, names)
        if found not in (None, "", []):
            config[key] = found
    if not config.get("chartType"):
        kind = item.get("type")
        if isinstance(kind, str) and kind not in {"row", "group", "container"}:
            config["chartType"] = kind
    return {**item, "valueConfig": config}


def _widget_field_keys(config: dict) -> list[str]:
    keys = []
    selected = config.get("selectedFields")
    if isinstance(selected, list):
        keys.extend(str(item) for item in selected if item)
    for key in ("dimensionField", "valueField"):
        if config.get(key):
            keys.append(str(config[key]))
    return keys


_REQUIRED_ROLE_PAIRS = {
    "dimensionField",
    "valueField",
    "topNLabelField",
    "topNValueField",
    "multiValueLabelField",
    "multiValueValueField",
}


def _role_value(config: dict, key: str):
    if "." in key:
        parent, child = key.split(".", 1)
        nested = config.get(parent)
        if isinstance(nested, dict):
            return nested.get(child)
        return None
    return config.get(key)


_LABEL_TERMS = ("名称", "分组", "对象", "name", "label", "title", "display", "model", "key", "category")
_VALUE_TERMS = ("费用", "合计", "数量", "实例", "占比", "健康", "count", "cost", "total", "amount", "score", "value", "pct", "rate", "percent")
_LABEL_ROLE_KEYS = {"dimensionField", "topNLabelField", "multiValueLabelField"}


def _field_semantics(field: dict) -> str:
    return " ".join(str(field.get(key) or "") for key in ("name", "title", "desc")).casefold()


def _semantic_role_field(fields: list[dict], *, label: bool, used: set[str], selected_names: set[str], source_text: str) -> dict | None:
    """按名称和说明推荐字段。展示和数值都会被页面转换，不看声明类型。"""
    terms = _LABEL_TERMS if label else _VALUE_TERMS
    avoid = _VALUE_TERMS if label else _LABEL_TERMS
    best = None
    best_score = None
    for index, field in enumerate(fields):
        name = str(field.get("name") or "")
        if not name or name in used:
            continue
        text = _field_semantics(field)
        matched = sum(1 for term in terms if term.casefold() in text)
        if matched <= 0:
            continue
        score = matched * 3
        score -= sum(3 for term in avoid if term.casefold() in text)
        if any(term.casefold() in source_text and term.casefold() in text for term in terms):
            score += 2
        if name in selected_names:
            score += 1
        if label and (name.casefold().endswith("_id") or text.endswith("id")):
            score -= 2
        if score <= 0:
            continue
        rank = (score, name in selected_names, -index)
        if best_score is None or rank > best_score:
            best = field
            best_score = rank
    return best


def _fill_missing_role_fields(config: dict, chart_type: str, source: dict) -> None:
    """必填的展示字段和数值字段为空时，按字段语义补上。不查询数据源。"""
    fields = [field for field in (source.get("fields") or []) if isinstance(field, dict) and field.get("name")]
    if not fields:
        return
    spec = widget_specs().get(str(chart_type or "")) or {}
    from apps.operation_analysis.services.dashboard_widget_draft import _set_role

    selected_names = {str(item) for item in (config.get("selectedFields") or []) if item}
    source_text = " ".join(str(source.get(key) or "") for key in ("name", "desc")).casefold()
    used: set[str] = set()
    for role in spec.get("roles") or []:
        if isinstance(role, dict):
            current = _role_value(config, str(role.get("key") or ""))
            if current not in (None, "", []):
                used.add(str(current))
    for role in spec.get("roles") or []:
        if not isinstance(role, dict) or not role.get("required"):
            continue
        key = str(role.get("key") or "")
        if key not in _REQUIRED_ROLE_PAIRS:
            continue
        if _role_value(config, key) not in (None, "", []):
            continue
        picked = _semantic_role_field(
            fields,
            label=key in _LABEL_ROLE_KEYS,
            used=used,
            selected_names=selected_names,
            source_text=source_text,
        )
        if picked is None or not picked.get("name"):
            continue
        _set_role(config, key, picked["name"])
        used.add(picked["name"])


def _label_widget(item: dict, config: dict, source: dict) -> dict:
    """单值卡用字段中文名做标题、字段说明做描述。趋势和表格保留数据源名称。"""
    fields = {str(field.get("name")): field for field in (source.get("fields") or []) if isinstance(field, dict) and field.get("name")}
    keys = _widget_field_keys(config)
    primary = fields.get(keys[0]) if keys else None
    title = str((primary or {}).get("title") or "").strip()
    description = str((primary or {}).get("desc") or "").strip()
    chart_type = str(config.get("chartType") or "")
    source_name = str(source.get("name") or "").strip()
    if chart_type not in {"single", "gauge"}:
        title = source_name or title
        description = str(source.get("desc") or "").strip() or description
    elif description == title:
        description = str(source.get("desc") or "").strip()
    name = str(item.get("name") or "").strip()
    raw_names = set(keys)
    raw_names.add(chart_type)
    if title and (not name or name in raw_names):
        name = title
    labeled = {**item, "name": name or source_name}
    current = str(item.get("description") or "").strip()
    if description and description != labeled["name"] and (not current or current in raw_names):
        labeled["description"] = description
    return labeled


_REFRESH_MS = {0: 0, 60: 60_000, 300: 300_000, 600: 600_000, 60_000: 60_000, 300_000: 300_000, 600_000: 600_000}
_PERCENT_TERMS = ("占比", "%", "percent", "pct")
_COUNT_TERMS = ("数量", "实例", "count")


def _refresh_ms(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return _REFRESH_MS.get(int(value))


def _valid_thresholds(value) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(isinstance(item, dict) and item.get("color") and item.get("value") not in (None, "") for item in value)


def _valid_mappings(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def _apply_display_format(config: dict, source: dict) -> None:
    """保留模型写上的单位、精度、阈值和值映射。没写时只按字段说明补占比或数量。"""
    factor = config.get("conversionFactor")
    if "conversionFactor" in config and (isinstance(factor, bool) or not isinstance(factor, (int, float))):
        config.pop("conversionFactor", None)
    places = config.get("decimalPlaces")
    if "decimalPlaces" in config and (isinstance(places, bool) or type(places) is not int or not 0 <= places <= 8):
        config.pop("decimalPlaces", None)
    if "thresholdColors" in config and not _valid_thresholds(config.get("thresholdColors")):
        config.pop("thresholdColors", None)
    if "valueMappings" in config and not _valid_mappings(config.get("valueMappings")):
        config.pop("valueMappings", None)
    if config.get("unitId") or "decimalPlaces" in config:
        return
    value_name = config.get("valueField") or config.get("topNValueField") or config.get("multiValueValueField")
    selected = config.get("selectedFields")
    if not value_name and isinstance(selected, list) and selected:
        value_name = selected[0]
    field = next((item for item in (source.get("fields") or []) if isinstance(item, dict) and item.get("name") == value_name), None)
    text = _field_semantics(field or {}).casefold()
    if any(term.casefold() in text for term in _PERCENT_TERMS):
        config["unitId"] = "percent"
        config["decimalPlaces"] = 2
    elif any(term.casefold() in text for term in _COUNT_TERMS):
        config["decimalPlaces"] = 0


def _page_settings(proposal: dict) -> dict:
    settings = {}
    other = proposal.get("otherConfig")
    if isinstance(other, dict) and other:
        settings["otherConfig"] = other
    refresh = _refresh_ms(proposal.get("refreshInterval"))
    if refresh is not None:
        settings["refreshInterval"] = refresh
    return settings


def prepare_dashboard_proposal(proposal: dict, briefs: list[dict]) -> dict:
    """补全固定参数并校验方案。不加载选项全量，也不预览数据。"""
    if not isinstance(proposal, dict) or proposal.get("schemaVersion") != SCHEMA_VERSION:
        return {"ok": False, "reason": "schema", "pending": []}
    if not isinstance(proposal.get("layout"), list):
        return {"ok": False, "reason": "layout", "pending": []}
    by_id = {brief.get("id"): brief for brief in briefs}
    pending = []
    layout = []
    skipped_scene = False
    for index, item in enumerate(proposal.get("layout") or []):
        if not isinstance(item, dict):
            return {"ok": False, "reason": "layout", "pending": []}
        item = _coerce_widget_item(item)
        config = dict(item.get("valueConfig") or {})
        chart_type = config.get("chartType") or config.get("sceneWidgetType")
        if chart_type in SCENE_CHART_TYPES:
            skipped_scene = True
            continue
        if chart_type not in AI_CHART_TYPES:
            return {"ok": False, "reason": "chart_type", "pending": [{"index": index, "chartType": chart_type}]}
        source = _brief_by_id(by_id, config.get("dataSource"))
        if source is None:
            pending.append({"index": index, "reason": "datasource_not_found", "dataSource": config.get("dataSource")})
            continue
        config["dataSource"] = source.get("id")
        if chart_type not in (source.get("chart_type") or []):
            return {
                "ok": False,
                "reason": "chart_type_mismatch",
                "pending": [
                    {
                        "index": index,
                        "chartType": chart_type,
                        "allowedChartTypes": list(source.get("chart_type") or []),
                        "fields": _brief_field_names(source),
                    }
                ],
            }
        known_fields = {field["name"] for field in source.get("fields") or []}
        unknown = sorted(name for name in _widget_fields(config) if name not in known_fields)
        if unknown:
            return {
                "ok": False,
                "reason": "unknown_field",
                "pending": [{"index": index, "fields": unknown, "allowedFields": sorted(known_fields)}],
            }
        _fill_missing_role_fields(config, chart_type, source)
        _apply_display_format(config, source)
        params = []
        provided = {param.get("name"): param for param in (config.get("dataSourceParams") or []) if isinstance(param, dict)}
        for declared in source.get("params") or []:
            current = dict(provided.get(declared["name"]) or {})
            current["name"] = declared["name"]
            current.setdefault("alias_name", declared.get("alias_name"))
            current.setdefault("type", declared.get("type"))
            current.setdefault("filterType", declared.get("filterType"))
            current.setdefault("required", declared.get("required"))
            if declared.get("inputConfig") and not isinstance(current.get("inputConfig"), dict):
                current["inputConfig"] = declared.get("inputConfig")
            _clear_label_used_as_value(current, declared)
            if current.get("value") in (None, "") and declared.get("default") not in (None, ""):
                current["value"] = declared.get("default")
            if declared.get("filterType") == "fixed" and declared.get("default") not in (None, ""):
                current["value"] = declared.get("default")
            if current.get("value") in (None, ""):
                choices = static_param_choices(declared)
                if choices:
                    current["value"] = choices[0]["value"]
            if declared.get("required") and current.get("value") in (None, "") and declared.get("filterType") != "filter":
                pending.append({"index": index, "reason": "required_param", "name": declared["name"]})
            params.append(current)
        config["dataSourceParams"] = params
        _normalize_table_columns(config)
        for param in params:
            options_error = _dynamic_source_error(param.get("inputConfig"), by_id)
            if options_error:
                return {"ok": False, "reason": options_error, "pending": [{"index": index, "name": param.get("name")}]}
        layout.append(_label_widget({**item, "valueConfig": config}, config, source))
    for filt in proposal.get("filters") or []:
        if not isinstance(filt, dict):
            return {"ok": False, "reason": "filter", "pending": []}
        options_error = _dynamic_source_error(filt.get("inputConfig"), by_id)
        if options_error:
            return {"ok": False, "reason": options_error, "pending": [{"id": filt.get("id")}]}
    packed = preserve_placed_widgets(layout)
    if pending:
        payload = {"ok": False, "reason": "pending", "pending": pending, "proposal": {**proposal, "layout": packed}}
        if any(isinstance(item, dict) and item.get("reason") == "datasource_not_found" for item in pending):
            payload["sources"] = _compact_source_index(briefs)
        return payload
    if skipped_scene and not packed:
        return {"ok": False, "reason": "chart_type", "pending": []}
    finished = {**proposal, "layout": packed, "filters": proposal.get("filters") or []}
    finished.pop("otherConfig", None)
    finished.pop("refreshInterval", None)
    finished.update(_page_settings(proposal))
    return {"ok": True, "proposal": finished, "pending": []}


PARAM_ASK_PREFIX = "还要先定这些参数"
PARAM_FILLED_PREFIX = "已把参数写进方案"


def static_param_choices(declared: dict) -> list[dict]:
    """选项只来自参数自己的静态声明，不按数据源名字分支。"""
    config = declared.get("inputConfig") if isinstance(declared.get("inputConfig"), dict) else {}
    source = config.get("optionsSource") if isinstance(config.get("optionsSource"), dict) else {}
    if source.get("type") != "static":
        return []
    choices = []
    for item in source.get("staticItems") or []:
        if isinstance(item, dict) and item.get("value") not in (None, ""):
            choices.append({"label": str(item.get("label") or item.get("value")), "value": item.get("value")})
    return choices


def recommend_param_value(choices: list[dict], utterance: str) -> dict | None:
    """用户原话只对上一个选项时用那个。否则有选项就用第一项作为默认值，不再追问。"""
    usable = [item for item in choices or [] if isinstance(item, dict) and item.get("value") not in (None, "")]
    if not usable:
        return None
    text = compact_text(user_utterance(utterance))
    hits = []
    if text:
        for item in usable:
            label = compact_text(str(item.get("label") or ""))
            value = compact_text(str(item.get("value") or ""))
            if (label and label in text) or (value and value in text):
                hits.append(item)
    unique = {str(item.get("value")): item for item in hits}
    if len(unique) == 1:
        return next(iter(unique.values()))
    return usable[0]


def proposal_has_param_gaps(proposal: dict | None) -> bool:
    if not isinstance(proposal, dict):
        return False
    for item in proposal.get("layout") or []:
        if not isinstance(item, dict):
            continue
        for param in (item.get("valueConfig") or {}).get("dataSourceParams") or []:
            if isinstance(param, dict) and param.get("required") and param.get("filterType") != "filter" and param.get("value") in (None, ""):
                return True
    return False


_RELATIVE_TIME_RE = re.compile(r"(?:默认(?:时间范围|时间|范围)?(?:为|是)?|过去|最近|近|前)\s*" r"(?P<count>\d{1,4})\s*(?P<unit>分钟|小时|天|日|周|个月|月)")
_RELATIVE_TIME_UNIT_MINUTES = {
    "分钟": 1,
    "小时": 60,
    "天": 1440,
    "日": 1440,
    "周": 10080,
    "个月": 43200,
    "月": 43200,
}
_MAX_RELATIVE_TIME_MINUTES = 525600


def _explicit_relative_time(utterance: str) -> tuple[int, str] | None:
    matched = _RELATIVE_TIME_RE.search(user_utterance(utterance))
    if not matched:
        return None
    count = int(matched.group("count"))
    unit = matched.group("unit")
    minutes = count * _RELATIVE_TIME_UNIT_MINUTES[unit]
    if minutes <= 0 or minutes > _MAX_RELATIVE_TIME_MINUTES:
        return None
    return minutes, f"{count}{unit}"


def _direct_param_answer(utterance: str) -> str:
    """用户单独回复的短值。确认、取消和搭盘句不是参数值。"""
    text = user_utterance(utterance).strip()
    compact = compact_text(text)
    if not compact or len(compact) > 24:
        return ""
    if classify_dashboard_request(text) != "none":
        return ""
    if compact in {"确认", "可以", "就这样", "符合", "是", "好", "好的", "行"}:
        return ""
    return re.sub(r"^(用|填|选择|选)", "", text).strip()


def fill_confirmed_param_values(proposal: dict, briefs: list[dict], utterance: str = "", choice_loader=None) -> tuple[dict, list[dict], list[str]]:
    """能确定的必填参数写进方案。确定不了的留给用户，不删组件。"""
    if not isinstance(proposal, dict):
        return proposal, [], []
    by_id = {brief.get("id"): brief for brief in briefs or [] if isinstance(brief, dict)}
    layout = []
    gaps = []
    notes = []
    explicit_time = _explicit_relative_time(utterance)
    for item in proposal.get("layout") or []:
        if not isinstance(item, dict):
            layout.append(item)
            continue
        config = dict(item.get("valueConfig") or {})
        brief = _brief_by_id(by_id, config.get("dataSource")) or {}
        provided = {
            param.get("name"): dict(param) for param in (config.get("dataSourceParams") or []) if isinstance(param, dict) and param.get("name")
        }
        declared_list = [param for param in (brief.get("params") or []) if isinstance(param, dict) and param.get("name")] or list(provided.values())
        next_params = []
        for declared in declared_list:
            current = dict(provided.get(declared.get("name")) or {})
            current["name"] = declared.get("name")
            current.setdefault("alias_name", declared.get("alias_name") or declared.get("name"))
            current.setdefault("type", declared.get("type") or "string")
            current.setdefault("filterType", declared.get("filterType") or "params")
            current.setdefault("required", bool(declared.get("required")))
            if declared.get("inputConfig") and not isinstance(current.get("inputConfig"), dict):
                current["inputConfig"] = declared.get("inputConfig")
            if current.get("type") == "timeRange" and explicit_time:
                current["value"] = explicit_time[0]
                notes.append(f"{item.get('name') or '组件'} 的「{current.get('alias_name')}」使用 {explicit_time[1]}")
                next_params.append(current)
                continue
            if not current.get("required") or current.get("filterType") == "filter" or current.get("value") not in (None, ""):
                next_params.append(current)
                continue
            choices = static_param_choices(declared)
            if not choices and callable(choice_loader):
                loaded = choice_loader(declared)
                choices = [item for item in loaded if isinstance(item, dict)] if isinstance(loaded, list) else []
            picked = recommend_param_value(choices, utterance)
            if picked:
                current["value"] = picked["value"]
                notes.append(f"{item.get('name') or '组件'} 的「{current.get('alias_name')}」使用 {picked.get('label') or picked.get('value')}")
            else:
                gaps.append(
                    {
                        "widget": item.get("name") or "组件",
                        "alias": current.get("alias_name") or current.get("name"),
                        "choices": choices,
                    }
                )
            next_params.append(current)
        if next_params:
            config["dataSourceParams"] = next_params
        layout.append({**item, "valueConfig": config})
    answer = _direct_param_answer(utterance)
    if answer and gaps:
        alias = gaps[0]["alias"]
        widget_name = gaps[0]["widget"]
        for item in layout:
            if not isinstance(item, dict) or (item.get("name") or "组件") != widget_name:
                continue
            config = dict(item.get("valueConfig") or {})
            params = []
            for param in config.get("dataSourceParams") or []:
                current = dict(param)
                if (current.get("alias_name") == alias or current.get("name") == alias) and current.get("value") in (None, ""):
                    current["value"] = answer
                params.append(current)
            item["valueConfig"] = {**config, "dataSourceParams": params}
            break
        notes.append(f"{widget_name} 的「{alias}」使用 {answer}")
        gaps = gaps[1:]
    return {**proposal, "layout": layout}, gaps, notes


def param_gap_reply(gaps: list[dict], notes: list[str] | None = None) -> str:
    first = gaps[0]
    choices = "、".join(str(item.get("label") or item.get("value")) for item in (first.get("choices") or [])[:8])
    lines = [f"{PARAM_ASK_PREFIX}：{first.get('widget')} 的「{first.get('alias')}」。"]
    if choices:
        lines.append(f"可选：{choices}")
    if notes:
        lines.append("已写入：")
        lines.extend(f"- {note}" for note in notes)
    if len(gaps) > 1:
        lines.append(f"还有 {len(gaps) - 1} 个参数，这个定完再问。")
    lines.append("回复要用的值。全部定完并校验通过后，我会直接套上画布。")
    return "\n".join(lines)


def param_filled_reply(notes: list[str]) -> str:
    body = "\n".join(f"- {note}" for note in notes)
    return f"{PARAM_FILLED_PREFIX}。\n{body}\n正在应用到画布。"


VISIBLE_BRIEF_LIMIT = 500


def list_visible_briefs(team_id: int, group_ids: list[int] | None = None) -> list[dict]:
    from django.db.models import Q

    from apps.operation_analysis.common.datasource_visibility import expand_datasource_org_query
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel

    ids = []
    for item in group_ids or [team_id]:
        if type(item) is int and item > 0 and item not in ids:
            ids.append(item)
    if not ids:
        return []
    if len(ids) == 1:
        membership = Q(groups__contains=ids[0])
    else:
        membership = Q()
        for gid in ids:
            membership |= Q(groups__contains=gid)
    briefs = []
    visible = expand_datasource_org_query(membership, include_all_builtins=False)
    queryset = (
        DataSourceAPIModel.objects.filter(visible)
        .only("id", "name", "desc", "chart_type", "params", "field_schema")
        .prefetch_related("tag")
        .order_by("id")[:VISIBLE_BRIEF_LIMIT]
    )
    for source in queryset:
        brief = brief_from_source(
            {
                "id": source.id,
                "name": source.name,
                "desc": source.desc,
                "tags": [tag.name for tag in source.tag.all()],
                "chart_type": source.chart_type or [],
                "params": source.params or [],
                "field_schema": source.field_schema or [],
            }
        )
        if brief:
            briefs.append(brief)
    return briefs


_MAX_WIDGETS = 12
_NUMBER_TYPES = {"number", "integer", "float", "int", "double"}
_TIME_TYPES = {"time", "datetime", "date", "timestamp"}
_METRIC_HINTS = ("percent", "usage", "count", "avg", "max", "min", "value", "cpu", "mem", "disk", "rate")
_LABEL_HINTS = ("name", "label", "title", "host", "display")
_RANK_HINTS = ("rank", "index", "order")
_PREFERRED_CHARTS = (
    "single",
    "gauge",
    "topN",
    "pie",
    "multiValue",
    "line",
    "bar",
    "table",
    "eventTable",
    "eventTimeline",
    "cardList",
    "nodeGraph",
    "radar",
    "topologyMap",
)
_REMOVE_RE = re.compile(r"删除|去掉|移除")
_REMOVE_NOISE = re.compile(r"去掉|删除|移除|不要了?|这个|那个|单值|组件|图表|卡片")
_PAGE_MARKERS = ("以下是用户当前正在查看的页面快照", "<current_page>", "## 仪表盘编辑状态")
_WIDGET_LINE_RE = re.compile(
    r"^- id=(?P<i>\S+)\s+name=(?P<name>.*?)\s+chart=(?P<chart>\S+)"
    r"(?:\s+nodeGraph=\S+)?"
    r"\s+dataSource=(?P<source>\S+)\s+fields=(?P<fields>.*?)\s+params=(?P<params>.*?)"
    r"\s+bindings=(?P<bindings>.*?)\s+pos=(?P<x>-?[\d.]+),(?P<y>-?[\d.]+),(?P<w>-?[\d.]+),(?P<h>-?[\d.]+)"
)
_ROLE_KEYS = {
    "selected": "selectedFields",
    "description": "descriptionField",
    "dimension": "dimensionField",
    "value": "valueField",
    "topNLabel": "topNLabelField",
    "topNValue": "topNValueField",
    "multiValueLabel": "multiValueLabelField",
    "multiValueValue": "multiValueValueField",
    "nodeSource": "nodeGraphSourceField",
    "nodeTarget": "nodeGraphTargetField",
    "nodeValue": "nodeGraphValueField",
    "nodePort": "nodeGraphTargetPortField",
    "timeline.time": "eventTimeline.timeField",
    "timeline.title": "eventTimeline.titleField",
    "timeline.description": "eventTimeline.descriptionField",
    "timeline.category": "eventTimeline.categoryField",
    "timeline.status": "eventTimeline.statusField",
    "timeline.link": "eventTimeline.linkField",
    "radar": None,
    "radarName": "radar.arrayNameField",
    "radarValue": "radar.arrayValueField",
    "cardTitle": "cardList.titleField",
    "cardDescription": "cardList.descriptionField",
    "cardLeading": "cardList.leading",
    "cardBadge": "cardList.badgeField",
    "cardTrailing": "cardList.trailingPrimaryField",
    "cardTrailing2": "cardList.trailingSecondaryField",
    "column": "tableConfig.columns",
}


def widget_specs() -> dict[str, dict]:
    specs = {}
    for item in load_widget_capabilities().get("widgets") or []:
        if isinstance(item, dict) and item.get("type"):
            specs[str(item["type"])] = item
    return specs


def compact_text(text: str) -> str:
    return re.sub(r"[\s，。！？、,.!；;：:（）()]+", "", str(text or ""))


def user_utterance(message: str) -> str:
    text = str(message or "")
    for marker in _PAGE_MARKERS:
        index = text.find(marker)
        if index >= 0:
            text = text[:index]
    text = text.strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return text


def is_widget_removal(message: str) -> bool:
    return bool(_REMOVE_RE.search(user_utterance(message)))


_DEFERRED_RE = re.compile(r"字段|筛选|单位|小数|阈值|精度|换算|值映射")
_UNSUPPORTED_RE = re.compile(r"分组|刷新周期|刷新间隔|另存|导出|网络拓扑|关联拓扑|场景组件|仪表盘改名|盘名")
_BUILD_RE = re.compile(r"搭盘|搭一个|搭建|搞一个|帮我.*仪表盘|加一张|加个|再加|新建.*仪表盘|创建.*仪表盘")
_DASHBOARD_CREATE_ACTION_RE = re.compile(r"搭建|创建|新建|新增|增加|生成|制作|配置|搞一个|做一个")
_DASHBOARD_NOUN_RE = re.compile(r"仪表盘|看板|大屏")
_EXTEND_ACTION_RE = re.compile(r"新增|增加|添加|加上|再加|补充")
_WIDGET_NOUN_RE = re.compile(r"图表|组件|卡片")
_IMPLICIT_WIDGET_GOAL_RE = re.compile(
    r"top\s*\d*|趋势|变化|走势|时间序列|分布|占比|比例|构成|明细|列表|清单|详情|" r"排行|排名|榜单|统计|计数|总数|数量|总量|概览|总览|概况|关系|依赖|拓扑",
    re.I,
)
_BUILD_NEGATION_RE = re.compile(r"(?:不想|不要|无需|别).{0,6}(?:搭建|创建|新建|新增|增加|生成|制作|配置)")
_SPLIT_RE = re.compile(r"加一张|加个|再加|搭一个|(?:新建|新增|增加|创建).*仪表盘")
_EDIT_RE = re.compile(r"改成|改为|换成|调成|调整|改名|标题|布局|每行|一行|宽度|高度|并排|挪到|移到|交换|删除|去掉|移除")
_REVISE_RE = _EDIT_RE
_CHART_ALIASES = (
    ("事件时间线", "eventTimeline"),
    ("时间线", "eventTimeline"),
    ("事件表格", "eventTable"),
    ("卡片列表", "cardList"),
    ("节点关系", "nodeGraph"),
    ("关系拓扑", "topologyMap"),
    ("柱状图", "bar"),
    ("柱状", "bar"),
    ("折线图", "line"),
    ("折线", "line"),
    ("饼图", "pie"),
    ("雷达图", "radar"),
    ("雷达", "radar"),
    ("多值", "multiValue"),
    ("单值", "single"),
    ("排行", "topN"),
    ("表格", "table"),
    ("卡片", "cardList"),
)
_TITLE_RE = re.compile(r"把(?P<src>.+?)的?(?:标题|名字)(?:改成|改为|换成)(?P<dst>.+)")
_DESC_RE = re.compile(r"把(?P<src>.+?)的说明(?:改成|改为|换成)(?P<dst>.+)")
_CHART_RE = re.compile(r"把(?P<src>.+?)(?:改成|换成|改为)(?P<chart>事件时间线|时间线|事件表格|卡片列表|节点关系图|关系拓扑|柱状图|柱状|折线图|折线|饼图|雷达图|雷达|多值指标|多值|单值指标|单值|排行|TopN|表格|卡片)")
_MOVE_RE = re.compile(r"把(?P<src>.+?)(?:挪到|移到)(?P<place>上面|下面|底部|左边|右边)")
_SIDE_RE = re.compile(r"把(?P<a>.+?)和(?P<b>.+?)并排")
_SWAP_RE = re.compile(r"交换(?P<a>.+?)和(?P<b>.+)")
_WIDTH_ONE_RE = re.compile(r"把(?P<src>.+?)的?宽度(?:改成|改为|为|到)(?P<size>\d+)")
_HEIGHT_ONE_RE = re.compile(r"把(?P<src>.+?)的?高度(?:改成|改为|为|到)(?P<size>\d+)")


def should_keep_existing_widgets(message: str, current: dict | None) -> bool:
    """已有组件时，「新增/添加」是追加，不能用一份新方案把原组件换掉。"""
    if not isinstance(current, dict) or not current.get("layout"):
        return False
    return bool(_EXTEND_ACTION_RE.search(user_utterance(message)))


def _creates_new_dashboard(utterance: str) -> bool:
    """「新增一个……仪表盘」是新建。盘名里的「概览」不算往当前盘追加组件。"""
    if not (_DASHBOARD_CREATE_ACTION_RE.search(utterance) and _DASHBOARD_NOUN_RE.search(utterance)):
        return False
    if _WIDGET_NOUN_RE.search(utterance):
        return False
    if re.search(r"(?:当前|这个|现有|已有).{0,12}(?:仪表盘|看板|大屏)|(?:仪表盘|看板|大屏)(?:上|里|中)", utterance):
        return False
    return True


def classify_dashboard_request(message: str) -> str:
    """按用户这句话决定方案处理类型：revise、build、extend 或不支持的类型。"""
    utterance = user_utterance(message)
    compact = compact_text(utterance)
    if not compact:
        return "none"
    if _creates_new_dashboard(utterance):
        return "build"
    implicit_widget = _WIDGET_NOUN_RE.search(utterance) or _IMPLICIT_WIDGET_GOAL_RE.search(utterance)
    if _EXTEND_ACTION_RE.search(utterance) and implicit_widget:
        return "extend"
    editing = bool(_EDIT_RE.search(compact) or _REMOVE_RE.search(compact))
    if _REMOVE_RE.search(compact) and _SPLIT_RE.search(utterance):
        return "split"
    if editing and _DEFERRED_RE.search(compact) and not _REMOVE_RE.search(compact):
        return "deferred"
    if editing and _UNSUPPORTED_RE.search(compact):
        return "unsupported"
    if editing:
        return "revise"
    semantic_build = _DASHBOARD_CREATE_ACTION_RE.search(utterance) and _DASHBOARD_NOUN_RE.search(utterance)
    if _BUILD_RE.search(utterance) or (semantic_build and not _BUILD_NEGATION_RE.search(utterance)):
        return "build"
    return "none"


def preserve_placed_widgets(layout: list[dict]) -> list[dict]:
    """已有坐标的组件保持原位，只给还没位置的新组件排版。"""
    from apps.operation_analysis.services.dashboard_widget_draft import pack_widgets

    placed = []
    missing = []
    for item in layout:
        if isinstance(item, dict) and item.get("x") is not None and item.get("y") is not None:
            placed.append(item)
        else:
            missing.append(item)
    if not missing:
        return placed
    return placed + pack_widgets(missing)


def _trim_clause(text: str) -> str:
    return re.sub(r"(吗|吧|了|啊|呀)+$", "", str(text or "").strip(" ，。！？、"))


def _match_widgets(layout: list[dict], needle: str) -> list[dict]:
    compact_needle = compact_text(_trim_clause(needle))
    if len(compact_needle) < 1:
        return []
    matched = []
    for item in layout:
        if not isinstance(item, dict):
            continue
        name = compact_text(str(item.get("name") or ""))
        widget_id = compact_text(str(item.get("i") or ""))
        if name and (name in compact_needle or compact_needle in name):
            matched.append(item)
        elif widget_id and widget_id in compact_needle:
            matched.append(item)
    return matched


def _one_widget(layout: list[dict], needle: str) -> tuple[dict | None, str]:
    matched = _match_widgets(layout, needle)
    if len(matched) == 1:
        return matched[0], ""
    if not matched:
        return None, "没有找到要改的组件，请说出组件标题。"
    names = "、".join(str(item.get("name") or item.get("i")) for item in matched)
    return None, f"匹配到多个组件（{names}），请说出完整标题。"


def _chart_type_from_text(text: str) -> str:
    folded = str(text or "")
    for label, chart_type in _CHART_ALIASES:
        if label.lower() in folded.lower():
            return chart_type
    return ""


def _small_positive_int(value: str) -> int | None:
    text = str(value or "").strip()
    if text.isdigit():
        number = int(text)
        return number if 1 <= number <= 12 else None
    digits = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if text in digits:
        return digits[text]
    if text == "十":
        return 10
    if text.startswith("十") and text[1:] in digits:
        return 10 + digits[text[1:]]
    return None


def _apply_uniform_layout(layout: list[dict], message: str) -> list[dict] | None:
    from apps.operation_analysis.services.dashboard_widget_draft import pack_widgets

    compact = compact_text(user_utterance(message))
    per_row_match = re.search(r"(?:每行|一行)(?:放|展示|显示|排|摆)?(?P<count>\d{1,2}|[一二两三四五六七八九十]{1,3})个", compact)
    width_match = re.search(r"宽(?:度)?(?:改为|改成|为|到)?(\d+)", compact)
    height_match = re.search(r"高(?:度)?(?:改为|改成|为|到)?(\d+)", compact)
    single_width = _WIDTH_ONE_RE.search(user_utterance(message))
    single_height = _HEIGHT_ONE_RE.search(user_utterance(message))
    if single_width and not re.search(r"布局|每行", single_width.group("src")):
        width_match = None
    if single_height and not re.search(r"布局|每行", single_height.group("src")):
        height_match = None
    per_row = _small_positive_int(per_row_match.group("count")) if per_row_match else None
    width = int(width_match.group(1)) if width_match else None
    height = int(height_match.group(1)) if height_match else None
    if per_row:
        width = width or max(1, 12 // max(1, per_row))
    if not width and height is None:
        return None
    if width:
        per = max(1, 12 // max(1, width))
        packed = pack_widgets(layout, per_row=per)
        if height is not None:
            packed = [{**item, "h": height} for item in packed]
        return packed
    return [{**item, "h": height} for item in layout]


def revise_dashboard_proposal(proposal: dict | None, message: str) -> dict:  # noqa: C901
    """在当前画布上改标题、说明、布局、图表类型或删除。认不出目标时返回 reply。"""
    from apps.operation_analysis.services.dashboard_widget_draft import widget_matches_removal

    if not isinstance(proposal, dict):
        return {"reply": "还看不到当前画布，不能改组件。"}
    layout = [dict(item) for item in (proposal.get("layout") or []) if isinstance(item, dict)]
    utterance = user_utterance(message)
    reply = ""
    if _REMOVE_RE.search(utterance):
        matched = [item for item in layout if widget_matches_removal(item, message)]
        if not matched:
            return {"reply": "没有找到要去掉的组件，请说出图上的标题。"}
        if len(matched) > 1:
            names = "、".join(str(item.get("name") or item.get("i")) for item in matched)
            return {"reply": f"匹配到多个组件（{names}），请说出完整标题。"}
        layout = [item for item in layout if item not in matched]
    title_match = _TITLE_RE.search(utterance)
    if title_match:
        widget, reply = _one_widget(layout, title_match.group("src"))
        if widget:
            widget["name"] = _trim_clause(title_match.group("dst"))
    desc_match = _DESC_RE.search(utterance)
    if desc_match and not reply:
        widget, reply = _one_widget(layout, desc_match.group("src"))
        if widget:
            widget["description"] = _trim_clause(desc_match.group("dst"))
    chart_match = _CHART_RE.search(utterance)
    if chart_match and not reply:
        widget, reply = _one_widget(layout, chart_match.group("src"))
        chart_type = _chart_type_from_text(chart_match.group("chart"))
        if widget and chart_type:
            config = dict(widget.get("valueConfig") or {})
            config["chartType"] = chart_type
            widget["valueConfig"] = config
    for pattern, key in ((_WIDTH_ONE_RE, "w"), (_HEIGHT_ONE_RE, "h")):
        found = pattern.search(utterance)
        if not found or reply or re.search(r"布局|每行", found.group("src")):
            continue
        widget, reply = _one_widget(layout, found.group("src"))
        if widget:
            widget[key] = int(found.group("size"))
    uniform = None if reply else _apply_uniform_layout(layout, message)
    if uniform is not None:
        layout = uniform
    move_match = _MOVE_RE.search(utterance)
    if move_match and not reply:
        widget, reply = _one_widget(layout, move_match.group("src"))
        if widget:
            place = move_match.group("place")
            bottom = max((int(item.get("y") or 0) + int(item.get("h") or 3) for item in layout), default=0)
            if place in {"下面", "底部"}:
                widget["y"] = bottom
                widget["x"] = 0
            elif place == "上面":
                widget["y"] = 0
            elif place == "左边":
                widget["x"] = 0
            elif place == "右边":
                widget["x"] = max(0, 12 - int(widget.get("w") or 4))
    side_match = _SIDE_RE.search(utterance)
    if side_match and not reply:
        left, left_reply = _one_widget(layout, side_match.group("a"))
        right, right_reply = _one_widget(layout, side_match.group("b"))
        reply = left_reply or right_reply
        if left and right:
            right["x"] = int(left.get("x") or 0) + int(left.get("w") or 4)
            right["y"] = left.get("y") or 0
    swap_match = _SWAP_RE.search(utterance)
    if swap_match and not reply:
        first, first_reply = _one_widget(layout, swap_match.group("a"))
        second, second_reply = _one_widget(layout, swap_match.group("b"))
        reply = first_reply or second_reply
        if first and second:
            for key in ("x", "y", "w", "h"):
                first[key], second[key] = second.get(key), first.get(key)
    if reply:
        return {"reply": reply}
    if layout == [dict(item) for item in (proposal.get("layout") or []) if isinstance(item, dict)] and not _REMOVE_RE.search(utterance):
        if _REVISE_RE.search(utterance):
            return {"reply": "没有识别出要改的标题、布局或图表，请说得更具体一些。"}
    return {
        "schemaVersion": proposal.get("schemaVersion") or SCHEMA_VERSION,
        "layout": layout,
        "filters": proposal.get("filters") or [],
    }
