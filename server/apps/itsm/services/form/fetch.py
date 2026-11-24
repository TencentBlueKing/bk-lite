"""字段取数：发布快照、最小结果映射及绑定身份/参数的提交凭据。"""

import copy
import hashlib
import json
import math
import re

from django.core import signing
from django.core.cache import cache

from apps.core.openapi.registry import default_registry
from apps.core.openapi.schema import serializer_to_schema
from apps.itsm.models import DataDictionary, DataTable
from apps.itsm.models.integration import Integration
from apps.itsm.services.integrations import execute

from .capabilities import FIELD_CAPABILITIES, validate_binding, validate_result

SALT = "itsm.field.fetch.v1"
REF = re.compile(r"^\$\{(form|user|query)\.([\w]+)\}$")
CHOICES = {"select", "multiselect", "radio", "checkbox", "cascade", "multiCascade"}


def walk(fields):
    for field in fields:
        yield field
        yield from walk(field.get("children", []))


def digest(value):
    def canonical(item):
        if isinstance(item, dict):
            return {str(k): canonical(v) for k, v in item.items()}
        if isinstance(item, set):
            return sorted((canonical(v) for v in item), key=str)
        if isinstance(item, (tuple, list)):
            return [canonical(v) for v in item]
        return item

    value = canonical(value)
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def dependencies(value):
    if isinstance(value, dict):
        return set().union(*(dependencies(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(dependencies(v) for v in value)) if value else set()
    match = REF.fullmatch(value) if isinstance(value, str) else None
    return {match[2]} if match and match[1] == "form" else set()


def read_path(value, path):
    if not path:
        return value
    for key in str(path).split("."):
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and key.isdigit() and int(key) < len(value):
            value = value[int(key)]
        else:
            raise ValueError(f"结果缺少字段路径：{path}")
    return value


def flatten_options(options):
    for option in options:
        yield {"value": option["value"], "label": option["label"]}
        yield from flatten_options(option.get("children", []))


def option_rows(data):
    """仅识别明确的常见列表容器；有歧义时要求显式映射。"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        candidates = [data[key] for key in ("items", "results", "list") if isinstance(data.get(key), list)]
        if len(candidates) == 1:
            return candidates[0]
        if not candidates and isinstance(data.get("data"), (dict, list)):
            return option_rows(data["data"])
    raise ValueError("未找到唯一选项列表，请填写选项 / 行数据路径（例如 data.items）")


def option_path(row, explicit, candidates, label):
    if explicit:
        return read_path(row, explicit)
    if isinstance(row, dict):
        for key in candidates:
            if key in row:
                return row[key]
    raise ValueError(f"无法识别{label}，请配置{label}路径")


def map_options(data, cfg, tree=False):
    seen, fills = set(), {}

    def build(rows, depth=0):
        if not isinstance(rows, list) or depth > 20:
            raise ValueError("级联选项必须为树形数组，最多 20 层")
        options = []
        for row in rows:
            value = option_path(row, cfg.get("value_path"), ("value", "id", "key"), "选项值")
            label = option_path(row, cfg.get("label_path"), ("label", "name", "title", "text"), "显示名称")
            if isinstance(value, bool) or not isinstance(value, (str, int, float)) or not isinstance(label, str):
                raise ValueError("选项值须为字符串或数字，名称须为字符串")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("选项值不能是非有限数值")
            if str(value) in seen or len(seen) >= 500:
                raise ValueError("选项值重复或超过 500 项")
            seen.add(str(value))
            option = {"value": value, "label": label[:200]}
            fills[str(value)] = {target: read_path(row, path) for target, path in (cfg.get("fill") or {}).items()}
            if tree and isinstance(row, dict) and row.get("children"):
                option["children"] = build(row["children"], depth + 1)
            options.append(option)
        return options

    return build(data), fills


def field_safe(item):
    if item.kind == "python":
        return True
    if item.kind != "api":
        return False
    if item.config.get("transport") == "external":
        return item.config.get("method") == "GET"
    service, _, path = item.config.get("path", "").partition("/")
    endpoint = default_registry.find(service, path, item.config.get("method", "GET"))
    if endpoint is None:
        return False
    return endpoint.method == "GET" or (
        endpoint.method == "POST" and endpoint.permission.endswith("-View") and bool(re.search(r"(^|/)(search|query|list|get|count)([-_/]|$)", path))
    )


def snapshot(item):
    if not item.is_enabled or not field_safe(item):
        raise ValueError("字段只能使用启用的查询 API 或隔离 Python 集成")
    return {
        "id": item.id,
        "name": item.name,
        "kind": item.kind,
        "config": copy.deepcopy(item.config),
        "version": item.updated_at.isoformat(),
    }


def validate_api_inputs(item, cfg):
    if item.kind == "api":
        if item.config.get("transport") == "external":
            from apps.itsm.services.external_api import input_serializer

            definition = item.config.get("request_schema") or {"properties": {}}
            serializer_class = input_serializer(definition)
        else:
            service, _, path = item.config["path"].partition("/")
            endpoint = default_registry.find(service, path, item.config.get("method", "GET"))
            serializer_class = endpoint.serializer_class
            definition = serializer_to_schema(serializer_class)
        if set(definition.get("required", [])) - cfg.get("inputs", {}).keys():
            raise ValueError("缺少必填 API 参数")
        if set(cfg.get("inputs", {})) - definition.get("properties", {}).keys():
            raise ValueError("接口参数不在 API 声明中")
        from rest_framework.exceptions import ValidationError

        serializer = serializer_class()
        for name, value in cfg.get("inputs", {}).items():
            if not dependencies(value) and not (isinstance(value, str) and REF.fullmatch(value)):
                try:
                    serializer.fields[name].run_validation(value)
                except ValidationError as exc:
                    raise ValueError(f"API 参数 {name} 无效：{exc.detail}") from exc


def freeze_schema(schema, domain, *, sampling_field=None):
    schema = copy.deepcopy(schema)
    fields = {f["key"]: f for f in walk(schema.get("fields", []))}
    graph = {}
    for field in fields.values():
        cfg = field.get("fetch")
        if not cfg:
            continue
        if cfg["source"] == "integration":
            item = Integration.objects.get(id=cfg.get("integration_id"), domain=domain)
            cfg["snapshot"] = snapshot(item)
            cfg["integration_kind"] = item.kind
            validate_api_inputs(item, cfg)
        else:
            model = DataTable if cfg["source"] == "table" else DataDictionary
            resource = model.objects.get(key=cfg.get("resource_key"), domain=domain)
            if cfg["source"] == "table":
                columns = set(resource.fields.values_list("key", flat=True))
                if set(cfg.get("inputs", {})) - columns:
                    raise ValueError("数据表筛选条件必须使用已定义的列")
                if not cfg.get("transform_id") and field["key"] != sampling_field:
                    paths = (
                        list((cfg.get("columns") or {}).values())
                        if cfg.get("mode") == "table"
                        else (
                            [cfg.get("label_path") or "label", cfg.get("value_path") or "value"]
                            if cfg.get("mode") == "options"
                            else [cfg.get("value_path", "").removeprefix("0.")]
                        )
                    )
                    if any(path not in columns for path in paths):
                        raise ValueError("数据表取值必须选择已定义的列")
            cfg.pop("snapshot", None)
        if cfg.get("transform_id"):
            item = Integration.objects.get(id=cfg["transform_id"], domain=domain, kind="python")
            cfg["transform_snapshot"] = snapshot(item)
        else:
            cfg.pop("transform_snapshot", None)
        validate_binding(field, inspect=field["key"] == sampling_field)
        rows_ref = cfg.get("inputs", {}).get("rows") if cfg.get("integration_kind") == "python" else None
        if isinstance(rows_ref, str):
            name = rows_ref.removeprefix("${form.").removesuffix("}")
            if fields.get(name, {}).get("type") not in {"table", "nestedTable"}:
                raise ValueError("Python rows 只能引用表格字段")
        refs = dependencies(cfg.get("inputs", {})) | dependencies(cfg.get("transform_params", {}))
        if field["key"] in refs or refs - fields.keys() or any(fields[k].get("state") == "hidden" for k in refs):
            raise ValueError("依赖字段不存在、隐藏或引用自身")
        graph.setdefault(field["key"], set()).update(refs)
        cfg["dependencies"] = sorted(refs)
        for target in cfg.get("fill") or {}:
            if (
                target not in fields
                or target == field["key"]
                or fields[target]["type"] not in {"input", "textarea", "number"}
                or fields[target].get("state") in {"hidden", "readonly", "disabled"}
            ):
                raise ValueError("联动填充目标不存在或指向自身")
            graph.setdefault(target, set()).add(field["key"])

    def visit(key, stack):
        if key in stack:
            raise ValueError("字段取数存在循环依赖")
        for parent in graph.get(key, set()):
            visit(parent, stack | {key})

    for key in graph:
        visit(key, set())
    return schema


def public_schema(schema, labels=None):
    schema = copy.deepcopy(schema)
    for field in walk(schema.get("fields", [])):
        if field.get("fetch"):
            cfg = field["fetch"]
            cfg.pop("snapshot", None)
            cfg.pop("transform_snapshot", None)
        if labels and field["key"] in labels:
            field["source"] = {"type": "static", "options": labels[field["key"]]}
    return schema


def principal(identity):
    return digest(
        [
            identity.user,
            identity.domain,
            identity.team_ids,
            identity.permission,
            identity.roles,
            identity.is_superuser,
            identity.credential_type,
            identity.token_scope,
        ]
    )


def bind(value, values, identity, query):
    if isinstance(value, dict):
        return {key: bind(item, values, identity, query) for key, item in value.items()}
    if isinstance(value, list):
        return [bind(item, values, identity, query) for item in value]
    match = REF.fullmatch(value) if isinstance(value, str) else None
    if not match:
        return value
    sources = {"form": values, "user": {"username": identity.user, "teams": identity.team_ids, "domain": identity.domain}, "query": query}
    if match[2] not in sources[match[1]]:
        raise ValueError(f"请先填写依赖参数：{match[2]}")
    return sources[match[1]][match[2]]


def active_snapshot(cfg, key, identity):
    snap = cfg.get(key)
    if not snap:
        raise ValueError("字段取数配置未发布，请重新发布表单")
    live = Integration.objects.get(id=snap["id"], domain=identity.domain)
    if not live.is_enabled:
        raise ValueError("绑定的集成已停用")
    frozen = copy.copy(live)
    frozen.kind, frozen.config = snap["kind"], snap["config"]
    if not field_safe(frozen):
        raise ValueError("绑定的接口不允许字段取数")
    return frozen


def assert_active(cfg, identity):
    if cfg.get("source") in {"table", "dictionary"}:
        model = DataTable if cfg["source"] == "table" else DataDictionary
        resource = model.objects.get(key=cfg["resource_key"], domain=identity.domain)
        if resource.team and not identity.is_superuser and not set(map(str, resource.team)).intersection(map(str, identity.team_ids)):
            raise PermissionError()
    for key in ["snapshot", "transform_snapshot"]:
        if cfg.get(key):
            active_snapshot(cfg, key, identity)


def execute_checked(item, inputs, identity):
    result = execute(item, inputs, identity)
    if result["status"] != "done":
        raise ValueError(f"字段取数失败：{result.get('code') or '请检查集成'}")
    return result["output"]


def fetch_source_data(cfg, params, identity, query, page, tree):
    if cfg["source"] == "integration":
        data = execute_checked(active_snapshot(cfg, "snapshot", identity), params, identity)
    else:
        model = DataTable if cfg["source"] == "table" else DataDictionary
        resource = model.objects.get(key=cfg["resource_key"], domain=identity.domain)
        if resource.team and not identity.is_superuser and not set(map(str, resource.team)).intersection(map(str, identity.team_ids)):
            raise PermissionError()
        if cfg["source"] == "table":
            rows = resource.rows.order_by("id")
            for column, value in params.items():
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", column):
                    raise ValueError("数据表过滤字段无效")
                rows = rows.filter(**{f"data__{column}": value})
            if query:
                column = cfg.get("label_path") or "name"
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", column):
                    raise ValueError("搜索字段须为数据表列")
                rows = rows.filter(**{f"data__{column}__icontains": query})
            data = list(rows.values_list("data", flat=True)[(page - 1) * 20 : page * 20 + 1])
        else:
            rows = resource.items.filter(is_enabled=True).order_by("order", "id")
            if tree:
                items = list(rows[:501])
                if len(items) > 500:
                    raise ValueError("级联字典最多支持 500 项")
                nodes = {r.id: {"value": r.key, "label": r.label, "children": []} for r in items}
                data = []
                for item in items:
                    if item.parent_id is None:
                        data.append(nodes[item.id])
                    elif item.parent_id in nodes:
                        nodes[item.parent_id]["children"].append(nodes[item.id])
                # 环及禁用父项下的孤立节点不可作为可选结果。
            else:
                if query:
                    rows = rows.filter(label__icontains=query)
                data = [{"value": r.key, "label": r.label} for r in rows[(page - 1) * 20 : page * 20 + 1]]
    return data


def fetch_field(schema, key, values, identity, *, context, query="", page=1, inspect=False):
    if inspect and context != "preview":
        raise ValueError("样本探查仅用于表单编辑调试")
    field = next((f for f in walk(schema.get("fields", [])) if f["key"] == key), None)
    if not field or not field.get("fetch"):
        raise ValueError("字段未配置取数")
    cfg = field["fetch"]
    tree = FIELD_CAPABILITIES.get(field["type"], {}).get("shape") == "tree"
    validate_binding(field, inspect=inspect)
    assert_active(cfg, identity)
    refs = cfg.get("dependencies", sorted(dependencies(cfg.get("inputs", {}))))
    if any(values.get(name) in (None, "", []) for name in refs):
        raise ValueError("请先填写依赖字段")
    params = bind(cfg.get("inputs", {}), values, identity, {"keyword": str(query)[:100], "page": max(1, int(page)), "page_size": 20})
    dependency_values = {name: values.get(name) for name in refs}
    stamp = {
        "binding": digest([field["type"], cfg]),
        "principal": principal(identity),
        "context": context,
        "deps": digest(dependency_values),
    }
    cache_key = "itsm-field:" + digest([stamp, params, query, page])
    mapped = None if inspect else cache.get(cache_key)
    if mapped is None:
        data = fetch_source_data(cfg, params, identity, query, page, tree)
        if not inspect or cfg.get("transform_snapshot"):
            data = read_path(data, cfg.get("list_path", ""))
        if cfg.get("transform_snapshot"):
            data = execute_checked(
                active_snapshot(cfg, "transform_snapshot", identity),
                {"rows": data, "params": bind(cfg.get("transform_params", {}), values, identity, {})},
                identity,
            )
        if inspect:

            def bounded(value, depth=0):
                if depth > 10:
                    return None
                if isinstance(value, list):
                    return [bounded(v, depth + 1) for v in value[:3]]
                if isinstance(value, dict):
                    return {k: bounded(v, depth + 1) for k, v in list(value.items())[:50]}
                return value[:500] if isinstance(value, str) else value

            sample = bounded(data)
            if len(json.dumps(sample, ensure_ascii=False).encode()) > 64000:
                raise ValueError("返回样本过大，请缩小查询范围")
            return {"sample": sample}
        if cfg["mode"] == "options" and not cfg.get("list_path"):
            data = option_rows(data)
        mapped = {"options": [], "fills": {}, "value": None, "has_more": False}
        if cfg["mode"] in {"options", "table"}:
            if not isinstance(data, list):
                raise ValueError("列表路径必须指向数组")
            mapped["has_more"] = len(data) > 20 if cfg["source"] in {"table", "dictionary"} else len(data) >= 20
            if tree:
                mapped["has_more"] = False
            else:
                data = data[:20] if cfg["source"] in {"table", "dictionary"} else data[:100]
        if cfg["mode"] == "options":
            mapped["options"], mapped["fills"] = map_options(data, cfg, tree)
        elif cfg["mode"] == "table":
            columns = cfg.get("columns") or {}
            if not columns:
                raise ValueError("请配置表格列映射")
            mapped["value"] = [{target: read_path(row, path) for target, path in columns.items()} for row in data]
        else:
            mapped["value"] = read_path(data, cfg.get("value_path", ""))
        if cfg["mode"] != "options":
            validate_result(field, mapped["value"])
        targets = {f["key"]: f for f in walk(schema.get("fields", []))}
        for fill in mapped["fills"].values():
            for target, value in fill.items():
                validate_result(targets[target], value)
        if len(json.dumps(mapped, ensure_ascii=False).encode()) > 128000:
            raise ValueError("映射结果过大，请缩小查询范围")
        cache.set(cache_key, mapped, 30)
    return {**mapped, "receipt": signing.dumps({**stamp, "field": key, "result": mapped}, salt=SALT, compress=True)}


def verify_fields(schema, values, identity, *, context, original=None, allowed=None):
    result = dict(values)
    original = original or {}
    labels = dict(original.get("_field_labels") or {})
    receipts = values.get("_field_receipts") or {}
    if not isinstance(receipts, dict):
        raise ValueError("字段取数凭据必须是对象")
    for field in walk(schema.get("fields", [])):
        key, cfg = field["key"], field.get("fetch")
        if not cfg or (allowed is not None and key not in allowed):
            continue
        validate_binding(field)
        refs = cfg.get("dependencies", [])
        if key in original and values.get(key) == original.get(key) and all(values.get(ref) == original.get(ref) for ref in refs):
            continue
        if values.get(key) in (None, "", []) and not field.get("required") and not cfg.get("enforce"):
            labels.pop(key, None)
            continue
        if identity is None:
            raise ValueError({key: "动态字段需要当前用户身份及取数校验"})
        assert_active(cfg, identity)
        expected = {
            "binding": digest([field["type"], cfg]),
            "principal": principal(identity),
            "context": context,
            "deps": digest({ref: values.get(ref) for ref in refs}),
        }
        valid = []
        for token in list(receipts.get(key) or [])[-20:]:
            try:
                proof = signing.loads(token, salt=SALT, max_age=900)
            except (signing.BadSignature, TypeError):
                continue
            if proof.get("field") == key and all(proof.get(k) == v for k, v in expected.items()):
                valid.append(proof["result"])
        if not valid:
            raise ValueError({key: "取数结果已失效，请刷新字段后重试"})
        if cfg["mode"] == "options":
            options = [option for proof in valid for option in flatten_options(proof["options"])]
            chosen = values.get(key) if isinstance(values.get(key), list) else [values.get(key)]
            selected = [option for option in options if option["value"] in chosen]
            if any(value not in [option["value"] for option in options] for value in chosen):
                raise ValueError({key: "选择值不在当前授权结果中"})
            labels[key] = list({str(option["value"]): option for option in selected}.values())
        elif field.get("state") in {"readonly", "disabled"} or cfg.get("enforce"):
            result[key] = valid[-1]["value"]
        if cfg["mode"] != "options" and result.get(key) not in (None, "", []):
            validate_result(field, result[key])
    result["_field_labels"] = labels
    result.pop("_field_receipts", None)
    return result


def task_fetch_context(ticket, task):
    return f"ticket:{ticket.id}:task:{task.id}"


def validate_submission(schema, values, identity, context, original=None, field_perm=None, *, receipt_context=None):
    """先按节点权限过滤，再验证取数凭据；只保存服务端验证过的标签。"""
    from apps.itsm.services.form.schema import LAYOUT_ONLY
    from apps.itsm.services.form.table_columns import TABLE_FIELDS, merge_table_rows
    from apps.itsm.services.form.validator import FormValidator, visible_field_keys

    original = original or {}
    validator = FormValidator(schema, field_perm)
    editable = {f.key: f for f, mode in validator._fields() if mode not in {"hidden", "readonly"} and f.type not in LAYOUT_ONLY}
    incoming = {key: value for key, value in values.items() if key in editable}
    for key, value in incoming.items():
        field = editable[key]
        if field.type in TABLE_FIELDS:
            incoming[key] = merge_table_rows(field.model_dump(), original.get(key), value, validator.field_perm, context)
    merged = {**original, **incoming}
    allowed = editable.keys() & visible_field_keys(validator.schema, merged)
    merged["_field_receipts"] = values.get("_field_receipts", {})
    verified = verify_fields(schema, merged, identity, context=receipt_context or context, original=original, allowed=allowed)
    # 动态选项由凭据验证，不能再拿旧静态选项二次判断。
    checked_schema = copy.deepcopy(schema)
    for field in walk(checked_schema.get("fields", [])):
        if field.get("fetch") and field["fetch"].get("mode") == "options":
            field["source"] = {"type": "static", "options": verified.get("_field_labels", {}).get(field["key"], [])}
    cleaned, errors = FormValidator(checked_schema, field_perm).merge(original, verified)
    if errors:
        raise ValueError(errors)
    if any(f.get("fetch") for f in walk(schema.get("fields", []))):
        cleaned["_field_labels"] = verified["_field_labels"]
    return cleaned
