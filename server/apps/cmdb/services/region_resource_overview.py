import json
from collections import defaultdict


REGION_TAG_KEY = "region"


def _parse_attrs(raw_attrs):
    if isinstance(raw_attrs, list):
        return raw_attrs
    if isinstance(raw_attrs, str):
        try:
            parsed = json.loads(raw_attrs.replace('\\"', '"'))
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def extract_region_options(models, visible_classification_ids):
    values = set()
    for model in models:
        if model.get("classification_id") not in visible_classification_ids:
            continue
        attrs = _parse_attrs(model.get("attrs"))
        tag_attr = next((
            attr for attr in attrs
            if isinstance(attr, dict)
            and attr.get("attr_id") == "tag"
            and attr.get("attr_type") == "tag"
        ), None)
        if not tag_attr:
            continue
        option = tag_attr.get("option")
        options = option.get("options") if isinstance(option, dict) else None
        if not isinstance(options, list):
            continue
        for item in options:
            if not isinstance(item, dict) or item.get("key") != REGION_TAG_KEY:
                continue
            value = str(item.get("value") or "").strip()
            if value:
                values.add(value)
    return [{"label": value, "value": value} for value in sorted(values)]


def build_region_resource_items(models, classifications, model_counts):
    classification_names = {
        item.get("classification_id"): item.get("classification_name", "")
        for item in classifications
        if item.get("classification_id")
    }
    totals = defaultdict(int)
    for model in models:
        classification_id = model.get("classification_id")
        model_id = model.get("model_id")
        if classification_id not in classification_names or not model_id:
            continue
        count = model_counts.get(model_id, 0)
        if isinstance(count, (int, float)) and count > 0:
            totals[classification_id] += count
    items = [
        {"label": classification_names[classification_id], "value": count}
        for classification_id, count in totals.items()
        if count > 0
    ]
    items.sort(key=lambda item: (-item["value"], item["label"]))
    return items
