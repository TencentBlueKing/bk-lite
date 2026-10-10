"""从检索候选生成组件，并从编辑状态还原当前画布。"""

from __future__ import annotations

import json
import re

from apps.operation_analysis.services.dashboard_proposal_service import (
    _LABEL_HINTS,
    _MAX_WIDGETS,
    _METRIC_HINTS,
    _NUMBER_TYPES,
    _PREFERRED_CHARTS,
    _RANK_HINTS,
    _REMOVE_NOISE,
    _REMOVE_RE,
    _ROLE_KEYS,
    _TIME_TYPES,
    _WIDGET_LINE_RE,
    SCENE_CHART_TYPES,
    SCHEMA_VERSION,
    compact_text,
    user_utterance,
    widget_specs,
)


def _field_kind(field: dict) -> str:
    field_type = str(field.get("type") or "").lower()
    if field_type in _NUMBER_TYPES:
        return "number"
    if field_type in _TIME_TYPES:
        return "time"
    if field_type in {"string", "text", "category"}:
        return "category"
    return "any"


def _unused(fields: list[dict], used: set[str]) -> list[dict]:
    return [field for field in fields if field.get("name") and field["name"] not in used]


def _pick_number(fields: list[dict], used: set[str]) -> dict | None:
    numbered = [field for field in _unused(fields, used) if _field_kind(field) == "number"]
    preferred = [field for field in numbered if any(hint in str(field.get("name") or "").lower() for hint in _METRIC_HINTS)]
    if preferred:
        return preferred[0]
    rest = [field for field in numbered if not any(hint in str(field.get("name") or "").lower() for hint in _RANK_HINTS)]
    if rest:
        return rest[0]
    if numbered:
        return numbered[0]
    hinted = [field for field in _unused(fields, used) if any(hint in str(field.get("name") or "").lower() for hint in _METRIC_HINTS)]
    return hinted[0] if hinted else None


def _pick_category(fields: list[dict], used: set[str]) -> dict | None:
    unused = _unused(fields, used)
    labeled = [field for field in unused if any(hint in str(field.get("name") or "").lower() for hint in _LABEL_HINTS)]
    if labeled:
        return labeled[0]
    non_number = [
        field for field in unused if _field_kind(field) != "number" and not any(hint in str(field.get("name") or "").lower() for hint in _RANK_HINTS)
    ]
    return non_number[0] if non_number else None


def _pick_time(fields: list[dict], used: set[str]) -> dict | None:
    timed = [field for field in _unused(fields, used) if _field_kind(field) == "time"]
    if timed:
        return timed[0]
    hinted = [field for field in _unused(fields, used) if any(token in str(field.get("name") or "").lower() for token in ("time", "date", "at"))]
    return hinted[0] if hinted else None


def _pick_field(fields: list[dict], kind: str, used: set[str]) -> dict | None:
    if kind == "number":
        return _pick_number(fields, used)
    if kind == "category":
        return _pick_category(fields, used)
    if kind == "time":
        return _pick_time(fields, used)
    unused = _unused(fields, used)
    return unused[0] if unused else None


def _set_role(config: dict, key: str, value) -> None:
    if key == "selectedFields":
        config["selectedFields"] = value if isinstance(value, list) else [value]
        return
    if key == "tableConfig.columns":
        names = value if isinstance(value, list) else [value]
        config["tableConfig"] = {"columns": [{"key": name, "title": name, "visible": True, "order": index} for index, name in enumerate(names)]}
        return
    if key == "cardList.leading":
        nested = dict(config.get("cardList") or {})
        nested["leading"] = {"type": "field", "field": value}
        config["cardList"] = nested
        return
    if "." in key:
        parent, child = key.split(".", 1)
        nested = dict(config.get(parent) or {})
        nested[child] = value
        config[parent] = nested
        return
    config[key] = value


def _fill_roles(config: dict, spec: dict, fields: list[dict], used: set[str]) -> bool:
    for role in spec.get("roles") or []:
        if not isinstance(role, dict) or not role.get("key"):
            continue
        key = str(role["key"])
        if key == "tableConfig.columns":
            names = [field["name"] for field in fields[:6]]
            if not names:
                return not role.get("required")
            _set_role(config, key, names)
            used.update(names)
            continue
        picked = _pick_field(fields, str(role.get("kind") or "any"), used)
        if picked is None:
            if role.get("required"):
                return False
            continue
        used.add(picked["name"])
        _set_role(config, key, picked["name"])
    return True


def _skip_rank_or_host_label(field: dict) -> bool:
    name = str(field.get("name") or "").lower()
    return any(hint in name for hint in _RANK_HINTS) or name.endswith("_host")


def _number_fields(fields: list[dict]) -> list[dict]:
    strict = [field for field in fields if _field_kind(field) == "number" and not _skip_rank_or_host_label(field)]
    if strict:
        return strict
    hinted = [
        field
        for field in fields
        if _field_kind(field) in {"number", "any"}
        and not _skip_rank_or_host_label(field)
        and any(hint in str(field.get("name") or "").lower() for hint in _METRIC_HINTS)
    ]
    return hinted


def _widget(source_id, name: str, chart_type: str, config: dict, spec: dict, description: str = "") -> dict:
    selected_fields = config.get("selectedFields") or []
    widget_key = selected_fields[0] if chart_type in {"single", "gauge"} and selected_fields else chart_type
    widget = {
        "i": f"ai-{source_id}-{widget_key}",
        "name": name,
        "w": spec.get("w") or 4,
        "h": spec.get("h") or 3,
        "valueConfig": {"chartType": chart_type, "dataSource": source_id, **config},
    }
    text = str(description or "").strip()
    if text and text != name:
        widget["description"] = text
    return widget


def _source_description(item: dict, spec: dict, field: dict | None = None) -> str:
    source_desc = str(item.get("desc") or "").strip()
    source_name = str(item.get("name") or "").strip()
    field_desc = str((field or {}).get("desc") or "").strip()
    label = str(spec.get("label") or spec.get("type") or "").strip()
    if source_desc:
        if field_desc and field_desc not in source_desc:
            return f"{source_desc}。本图使用字段 {field_desc}。"
        return source_desc
    if field_desc and source_name:
        return f"来自「{source_name}」的{label or '组件'}，展示 {field_desc}。"
    if source_name:
        return f"来自「{source_name}」的{label or '组件'}。"
    return ""


def _widgets_from_candidate(item: dict, specs: dict[str, dict]) -> list[dict]:
    fields = [field for field in (item.get("fields") or []) if isinstance(field, dict) and field.get("name")]
    charts = [str(chart) for chart in (item.get("chart_type") or [])]
    chart_type = next((chart for chart in _PREFERRED_CHARTS if chart in charts), charts[0] if charts else "")
    spec = specs.get(chart_type)
    if not spec:
        return []
    source_id = item.get("id")
    source_name = str(item.get("name") or "组件")
    if spec.get("expand") == "numberFields":
        widgets = []
        for field in _number_fields(fields)[:6]:
            label = str(field.get("desc") or field.get("name"))
            config = {}
            _set_role(config, "selectedFields", field["name"])
            widgets.append(_widget(source_id, label, chart_type, config, spec, _source_description(item, spec, field)))
        return widgets
    used: set[str] = set()
    config: dict = {}
    if not _fill_roles(config, spec, fields, used):
        return []
    return [_widget(source_id, source_name, chart_type, config, spec, _source_description(item, spec))]


def pack_widgets(layout: list[dict], columns: int = 12, per_row: int = 3) -> list[dict]:
    """按一行三个组件从左到右、从上到下排。"""
    cell_w = max(1, int(columns) // max(1, int(per_row)))
    x = y = row_h = 0
    packed = []
    for item in layout:
        width = cell_w
        height = int(item.get("h") or 3)
        if x + width > columns:
            x = 0
            y += row_h
            row_h = 0
        packed.append({**item, "x": x, "y": y, "w": width, "h": height})
        x += width
        row_h = max(row_h, height)
    return packed


def append_dashboard_widgets(current: dict | None, additions: dict | None) -> dict | None:
    """在当前画布底部追加新组件，不重排、不覆盖已有组件。"""
    if not isinstance(current, dict) or not isinstance(additions, dict):
        return None
    existing = [dict(item) for item in (current.get("layout") or []) if isinstance(item, dict)]
    known = {
        (
            (item.get("valueConfig") or {}).get("dataSource"),
            (item.get("valueConfig") or {}).get("chartType"),
            tuple((item.get("valueConfig") or {}).get("selectedFields") or []),
        )
        for item in existing
    }
    fresh = []
    for item in additions.get("layout") or []:
        if not isinstance(item, dict):
            continue
        config = item.get("valueConfig") or {}
        signature = (config.get("dataSource"), config.get("chartType"), tuple(config.get("selectedFields") or []))
        if signature in known:
            continue
        known.add(signature)
        fresh.append(dict(item))
    bottom = max((int(item.get("y") or 0) + int(item.get("h") or 3) for item in existing), default=0)
    if fresh:
        top = min(int(item.get("y") or 0) for item in fresh)
        fresh = [{**item, "y": int(item.get("y") or 0) - top + bottom} for item in fresh]
    return {
        **current,
        "schemaVersion": current.get("schemaVersion") or SCHEMA_VERSION,
        "layout": existing + fresh,
        "filters": current.get("filters") or [],
    }


def draft_proposal_from_candidates(candidates: list[dict]) -> dict | None:
    """按图表角色从数据源生成组件，不按 schema 顺序取字段，也不拆 metric_type。"""
    specs = widget_specs()
    layout = []
    for item in candidates or []:
        if not isinstance(item, dict) or item.get("id") in (None, ""):
            continue
        for widget in _widgets_from_candidate(item, specs):
            layout.append(widget)
            if len(layout) >= _MAX_WIDGETS:
                break
        if len(layout) >= _MAX_WIDGETS:
            break
    if not layout:
        return None
    return {"schemaVersion": SCHEMA_VERSION, "layout": pack_widgets(layout), "filters": []}


def removal_clauses(message: str) -> list[str]:
    """去掉后面的第一小句是目标标题，后面的解释不参与匹配。"""
    clauses = []
    for part in _REMOVE_RE.split(user_utterance(message))[1:]:
        clause = re.split(r"[，。！？；,]", part, maxsplit=1)[0]
        compact = compact_text(_REMOVE_NOISE.sub("", clause))
        if len(compact) >= 2:
            clauses.append(compact)
    return clauses


def widget_matches_removal(item: dict, message: str) -> bool:
    utterance = compact_text(user_utterance(message))
    name = compact_text(str(item.get("name") or ""))
    widget_id = compact_text(str(item.get("i") or item.get("id") or ""))
    if widget_id and widget_id in utterance:
        return True
    if name and name in utterance:
        return True
    return any(clause and (clause in name or name in clause) for clause in removal_clauses(message) if name)


def drop_named_widgets(proposal: dict, message: str) -> dict:
    """从当前方案去掉用户点名的组件，其余组件连同 id 原样保留。"""
    kept = []
    for item in proposal.get("layout") or []:
        if isinstance(item, dict) and widget_matches_removal(item, message):
            continue
        kept.append(item)
    return {
        **proposal,
        "schemaVersion": proposal.get("schemaVersion") or SCHEMA_VERSION,
        "layout": kept,
        "filters": proposal.get("filters") or [],
    }


def removal_outcome(message: str) -> str | None:
    """unique：刚好去掉一个；many：多个；none：一个都没对上。不是删除句返回 None。"""
    if not _REMOVE_RE.search(user_utterance(message)):
        return None
    current = proposal_from_edit_state(message)
    if not current:
        return None
    before = [item for item in current.get("layout") or [] if isinstance(item, dict)]
    dropped = [item for item in before if widget_matches_removal(item, message)]
    if len(dropped) == 1:
        return "unique"
    if len(dropped) > 1:
        return "many"
    return "none"


def _maybe_int(value):
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    return value if value not in ("", None) else None


def _config_from_edit_fields(chart: str, source, fields_text: str) -> dict:
    config: dict = {"chartType": chart, "dataSource": _maybe_int(source)}
    selected = []
    columns = []
    for part in (fields_text or "").split(","):
        if ":" not in part:
            continue
        role, value = part.split(":", 1)
        if not value:
            continue
        if role == "selected":
            selected.append(value)
            continue
        if role == "column":
            columns.append(value)
            continue
        key = _ROLE_KEYS.get(role)
        if key:
            _set_role(config, key, value)
    if selected:
        config["selectedFields"] = selected
    if columns:
        _set_role(config, "tableConfig.columns", columns)
    return config


def dashboard_snapshot_from_message(message: str) -> dict | None:
    """读取 page_context 中版本化的仪表盘 JSON 快照。"""
    text = str(message or "")
    marker = "## 仪表盘编辑状态"
    start = text.find(marker)
    if start < 0:
        return None
    content = text[start + len(marker) :].lstrip()
    try:
        snapshot, _end = json.JSONDecoder().raw_decode(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(snapshot, dict) or snapshot.get("snapshotVersion") != SCHEMA_VERSION:
        return None
    if not isinstance(snapshot.get("layout"), list) or not isinstance(snapshot.get("filters"), list):
        return None
    return snapshot


def _proposal_from_structured_snapshot(snapshot: dict) -> dict | None:
    layout = []
    for item in snapshot.get("layout") or []:
        if not isinstance(item, dict) or item.get("itemType") == "group":
            continue
        config = item.get("valueConfig")
        if not isinstance(config, dict):
            continue
        chart_type = config.get("sceneWidgetType") or config.get("chartType")
        if chart_type in SCENE_CHART_TYPES:
            continue
        layout.append(item)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "dashboardId": snapshot.get("dashboardId") or "current",
        "layout": layout,
        "filters": [item for item in (snapshot.get("filters") or []) if isinstance(item, dict)],
        "filterValues": snapshot.get("filterValues") if isinstance(snapshot.get("filterValues"), dict) else {},
        "otherConfig": snapshot.get("otherConfig") if isinstance(snapshot.get("otherConfig"), dict) else {},
        "refreshInterval": snapshot.get("refreshInterval") or 0,
    }


def proposal_from_edit_state(message: str) -> dict | None:
    """把页面快照里的仪表盘编辑状态还原成方案 JSON。"""
    snapshot = dashboard_snapshot_from_message(message)
    if snapshot is not None:
        return _proposal_from_structured_snapshot(snapshot)

    # 兼容混合版本发布期间仍使用旧文本快照的 Web 客户端。
    layout = []
    in_widgets = False
    for raw in str(message or "").splitlines():
        line = raw.strip()
        if line.startswith("widgets:"):
            in_widgets = True
            continue
        if in_widgets and (line.startswith("scenes:") or line.startswith("groups:") or line.startswith("filters:")):
            break
        if not in_widgets or line in {"", "- none"}:
            continue
        matched = _WIDGET_LINE_RE.match(line)
        if not matched:
            continue
        values = matched.groupdict()
        layout.append(
            {
                "i": values["i"],
                "name": values["name"],
                "x": float(values["x"]) if "." in values["x"] else int(float(values["x"])),
                "y": float(values["y"]) if "." in values["y"] else int(float(values["y"])),
                "w": float(values["w"]) if "." in values["w"] else int(float(values["w"])),
                "h": float(values["h"]) if "." in values["h"] else int(float(values["h"])),
                "valueConfig": _config_from_edit_fields(values["chart"], values["source"], values["fields"]),
            }
        )
    if not layout:
        return None
    return {"schemaVersion": SCHEMA_VERSION, "layout": layout, "filters": []}


def current_dashboard_proposal(message: str, stored: dict | None) -> dict | None:
    return proposal_from_edit_state(message) or (stored if isinstance(stored, dict) else None)


def _inventory_fields(config: dict) -> str:
    parts = []
    for name in config.get("selectedFields") or []:
        if name:
            parts.append(str(name))
    for key in (
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
        if value:
            parts.append(str(value))
    for column in (config.get("tableConfig") or {}).get("columns") or []:
        if isinstance(column, dict) and column.get("key"):
            parts.append(str(column["key"]))
    seen = []
    for part in parts:
        if part not in seen:
            seen.append(part)
    return "、".join(seen)


def _inventory_params(config: dict) -> str:
    names = []
    for param in config.get("dataSourceParams") or []:
        if not isinstance(param, dict) or not param.get("name"):
            continue
        names.append(str(param.get("alias_name") or param["name"]))
    return "、".join(names)


def _inventory_bindings(config: dict) -> str:
    return "、".join(key for key, enabled in (config.get("filterBindings") or {}).items() if enabled)


def _inventory_layout_summary(layout: list) -> str:
    """根据方案的真实坐标生成布局说明，避免回复与实际应用的方案不一致。"""
    items = [item for item in layout if isinstance(item, dict)]
    widths = {item.get("w") for item in items}
    heights = {item.get("h") for item in items}
    if len(widths) == 1:
        width = next(iter(widths))
        if isinstance(width, (int, float)) and width > 0:
            per_row = max(1, int(12 // width))
            if len(heights) == 1:
                height = next(iter(heights))
                if isinstance(height, (int, float)) and height > 0:
                    return f"布局：每行最多 {per_row} 个组件，每个宽 {width:g}、高 {height:g}。"
            return f"布局：每行最多 {per_row} 个组件，每个宽 {width:g}；组件高度保持各自设置。"
    return "布局：各组件的位置与尺寸按方案设置。"


def format_proposal_inventory(proposal: dict) -> str:
    """给用户看的方案清单：标题、说明、图表类型、数据源、字段、参数。"""
    specs = widget_specs()
    blocks = []
    for index, item in enumerate(proposal.get("layout") or [], start=1):
        if not isinstance(item, dict):
            continue
        config = item.get("valueConfig") or {}
        chart_type = str(config.get("chartType") or "")
        label = str((specs.get(chart_type) or {}).get("label") or chart_type)
        source_id = config.get("dataSource")
        lines = [f"{index}. {item.get('name') or label or '组件'}"]
        description = str(item.get("description") or "").strip()
        if description:
            lines.append(f"   - 说明: {description}")
        lines.append(f"   - 图表类型: {chart_type}" + (f"（{label}）" if label and label != chart_type else ""))
        lines.append(f"   - 数据源: {source_id}")
        fields = _inventory_fields(config)
        if fields:
            lines.append(f"   - 字段: {fields}")
        params = _inventory_params(config)
        if params:
            lines.append(f"   - 参数: {params}")
        bindings = _inventory_bindings(config)
        if bindings:
            lines.append(f"   - 绑定: {bindings}")
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    layout_summary = _inventory_layout_summary(proposal.get("layout") or [])
    return "已生成并校验仪表盘方案。以下是本次方案的组件清单：\n\n" + "\n\n".join(blocks) + f"\n\n{layout_summary}\n正在应用到当前画布。"
