from collections import defaultdict

from apps.cmdb.constants.constants import ENCRYPTED_KEY, INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.change_record_snapshot import load_attribute_snapshot
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.operation_service import OperationService
from apps.cmdb.services.transfer_authorization import TransferAuthorization
from apps.cmdb.services.transfer_service import TransferError, fingerprint
from apps.cmdb.services.unique_rule import collect_instance_unique_conflicts
from apps.cmdb.utils.base import format_groups_params
from apps.cmdb.utils.Import import Import
from apps.cmdb.validators import FieldValidator
from apps.core.exceptions.base_app_exception import BaseAppException


class TransferImport:
    @staticmethod
    def _public_reason(field_id, reason):
        if field_id in ENCRYPTED_KEY:
            return "凭据字段格式不正确"
        return reason

    @staticmethod
    def _record(errors, number, importer, field_id, reason):
        errors.append((number, importer.column_label(field_id), field_id or "", TransferImport._public_reason(field_id, reason)))

    @staticmethod
    def _unique_write_failure(exc, check):
        """仅识别写图前的唯一性拒绝。其它异常仍上抛，避免把未确认写入当成行失败。"""
        message = getattr(exc, "message", "") or ""
        if "exist；" not in message and "与现有实例冲突" not in message and "与本批次数据冲突" not in message:
            return None
        names = check.get("is_only") or {}
        for field_id, name in names.items():
            if name and name in message:
                return field_id, f"{name}已存在" if "exist；" in message else message
        field_id = next(iter(names), "")
        if "exist；" in message:
            return field_id, message.replace(" exist；", "已存在").replace("exist；", "已存在")
        return field_id, message

    @staticmethod
    def _distinct_identity_values(batch, field):
        """同一字段按值去重。下拉枚举会把单选收成列表，不能直接放进 set。"""
        seen = set()
        values = []
        for row in batch:
            value = row[1].get(field)
            if value is None:
                continue
            key = fingerprint(value)
            if key in seen:
                continue
            seen.add(key)
            values.append(value)
        return values

    @staticmethod
    def _canonical_identity_value(attr, value):
        """单选枚举把选项 id、选项名和 ``[id]`` 收成同一个匹配键。"""
        if not isinstance(attr, dict) or attr.get("attr_type") != "enum" or value in (None, "", []):
            return value
        id_by_token = {}
        for item in attr.get("option") or []:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            option_id = item["id"]
            id_by_token[str(option_id)] = option_id
            name = item.get("name")
            if name not in (None, ""):
                id_by_token[str(name)] = option_id

        def one(raw):
            if isinstance(raw, (list, tuple, dict, set)):
                return raw
            mapped = id_by_token.get(str(raw))
            return raw if mapped is None else mapped

        multiple = (attr.get("enum_select_mode") or "single") == "multiple"
        if isinstance(value, (list, tuple)):
            mapped = [one(item) for item in value]
            if not multiple and len(mapped) == 1:
                return mapped[0]
            return mapped
        return one(value)

    @staticmethod
    def _identity_fingerprint(identities, attrs_by_id, source):
        values = []
        for field in identities:
            raw = source.get(field) if isinstance(source, dict) else None
            values.append(TransferImport._canonical_identity_value(attrs_by_id.get(field) or {}, raw))
        return fingerprint(values)

    @staticmethod
    def _legacy_enum_scalars(attr, scalars):
        """枚举列表里的选项 id，以及该字段上保存成选项名或选项 id 的字符串。"""
        names_by_id = {}
        id_by_name = {}
        if isinstance(attr, dict) and attr.get("attr_type") == "enum":
            for item in attr.get("option") or []:
                if not isinstance(item, dict) or item.get("id") is None:
                    continue
                option_id = item["id"]
                name = item.get("name")
                if name not in (None, ""):
                    names_by_id.setdefault(str(option_id), []).append(name)
                    id_by_name[str(name)] = option_id
        legacy = []
        seen = set()

        def add(value):
            key = (type(value).__name__, value)
            if key in seen:
                return
            seen.add(key)
            legacy.append(value)

        for scalar in scalars:
            add(scalar)
            token = str(scalar)
            mapped = id_by_name.get(token)
            if mapped is not None:
                add(mapped)
                token = str(mapped)
            for name in names_by_id.get(token, []):
                add(name)
        return legacy

    @staticmethod
    def _field_filter_alternatives(field, attr, values):
        """字符串唯一值仍走原查询。列表值同时按成员和旧字符串两种形态查找。"""
        attr = attr or {}
        if not any(isinstance(value, (list, tuple)) for value in values):
            query_type = "int[]" if attr.get("attr_type") == "int" else "str[]"
            return [[{"field": field, "type": query_type, "value": values}]]
        scalars = []
        seen = set()
        for value in values:
            members = value if isinstance(value, (list, tuple)) else [value]
            for member in members:
                if member in (None, "") or isinstance(member, (list, tuple, dict, set)):
                    continue
                key = (type(member).__name__, member)
                if key in seen:
                    continue
                seen.add(key)
                scalars.append(member)
        alternatives = []
        if scalars:
            alternatives.append([{"field": field, "type": "list_any[]", "value": scalars}])
        legacy = TransferImport._legacy_enum_scalars(attr, scalars)
        if legacy:
            alternatives.append([{"field": field, "type": "str[]", "value": legacy}])
        if not alternatives:
            alternatives.append([{"field": field, "type": "str[]", "value": []}])
        return alternatives

    @staticmethod
    def _combine_filters(groups):
        combos = [[]]
        for alternatives in groups:
            combos = [current + alternative for current in combos for alternative in alternatives]
        return combos

    @staticmethod
    def _load_unique_conflict_candidates(model_id, identities, attrs, batch, candidates, seen_ids):
        """按单个唯一字段补齐冲突候选。查不到或超上限时不阻断导入，写入期再兜底。"""
        attrs_by_id = {item["attr_id"]: item for item in attrs}
        for field in identities:
            values = TransferImport._distinct_identity_values(batch, field)
            if not values:
                continue
            for alternative in TransferImport._field_filter_alternatives(field, attrs_by_id.get(field), values):
                param = alternative[0]
                if not param["value"]:
                    continue
                cursor = None
                while len(candidates) < 5000:
                    page_params = [
                        {"field": "model_id", "type": "str=", "value": model_id},
                        param,
                    ]
                    if cursor is not None:
                        page_params.append({"field": "inst_uuid", "type": "str>", "value": cursor})
                    with GraphClient() as graph:
                        found, _ = graph.query_entity(INSTANCE, page_params, page={"skip": 0, "limit": 500}, order="inst_uuid", include_count=False)
                    for existing in found:
                        key = existing.get("_id", existing.get("inst_uuid"))
                        if key not in seen_ids:
                            seen_ids.add(key)
                            candidates.append(existing)
                    if len(found) < 500:
                        break
                    cursor = found[-1]["inst_uuid"]

    @staticmethod
    def _match_batch(model_id, identities, attrs, batch, progress, offset, summary, total):
        """更新按全部唯一字段组合匹配；单字段查询只补冲突候选。"""
        attrs_by_id = {item["attr_id"]: item for item in attrs}
        groups = [
            TransferImport._field_filter_alternatives(field, attrs_by_id.get(field), TransferImport._distinct_identity_values(batch, field))
            for field in identities
        ]
        matches = defaultdict(list)
        candidates = []
        seen_ids = set()
        matched_keys = set()
        combo_matched = False
        for combo in TransferImport._combine_filters(groups):
            params = [{"field": "model_id", "type": "str=", "value": model_id}, *combo]
            if not all(param["value"] for param in params):
                continue
            combo_matched = True
            cursor = None
            while True:
                page_params = params + ([{"field": "inst_uuid", "type": "str>", "value": cursor}] if cursor else [])
                with GraphClient() as graph:
                    found, _ = graph.query_entity(INSTANCE, page_params, page={"skip": 0, "limit": 500}, order="inst_uuid", include_count=False)
                for existing in found:
                    key = existing.get("_id", existing.get("inst_uuid"))
                    if key not in matched_keys:
                        matched_keys.add(key)
                        matches[TransferImport._identity_fingerprint(identities, attrs_by_id, existing)].append(existing)
                    if key not in seen_ids:
                        seen_ids.add(key)
                        candidates.append(existing)
                if sum(map(len, matches.values())) > 10000:
                    raise TransferError("ambiguous_identity", "匹配到过多重复标识，请先清理实例唯一性")
                if len(found) < 500:
                    break
                cursor = found[-1]["inst_uuid"]
                progress(offset, total, summary, "matching")
        if not (combo_matched and len(identities) == 1):
            TransferImport._load_unique_conflict_candidates(model_id, identities, attrs, batch, candidates, seen_ids)
        return matches, candidates

    @staticmethod
    def _execute_instance_write(task, context, check, before, item, number):
        data = {key: value for key, value in item.items() if key != "model_id"}
        if before:
            data = {key: value for key, value in data.items() if check["editable"].get(key) or key == "organization"}
        action = "update" if before else "create"
        event_context = {"attribute_snapshot": load_attribute_snapshot(task.model_id, data.keys())}
        if before:
            event_context["before_data"] = before
        operation = OperationService.start(
            operator=context.actor.username,
            idempotency_key=f"transfer:{task.pk}:{number}",
            action=f"instance.{action}",
            target={"model_id": task.model_id, **({"inst_uuid": before["inst_uuid"]} if before else {})},
            request_payload={"update_attr": data} if before else data,
            event_context=event_context,
        ).operation

        # 从此边界起任何异常都可能已有写入，由任务边界置为失败并保留未确认提示，绝不猜测失败后继续/重放。
        def write(operation_id):
            common = dict(allowed_org_ids=context.teams, record_change=False, operation_id=operation_id, schedule_post_actions=False)
            if before:
                return InstanceManage.instance_update_by_uuid(
                    format_groups_params(context.teams),
                    context.actor.roles,
                    before["inst_uuid"],
                    data,
                    context.actor.username,
                    **common,
                )
            return InstanceManage.instance_create(task.model_id, data, context.actor.username, **common)

        try:
            return OperationService.execute_graph(operation, graph_write=write, events=OperationService.events_for_operation(operation)), None
        except BaseAppException as exc:
            unique_failure = TransferImport._unique_write_failure(exc, check)
            if unique_failure is None:
                raise
            return None, unique_failure

    @staticmethod
    def run(task, stream, context, progress):
        attrs = ModelManage.search_model_attr_v2(task.model_id)
        importer = Import(task.model_id, attrs, [], context.actor.username)
        rows = list(importer.iter_transfer_rows(stream, context.teams))
        if sum(len(names) for row in rows for names in row[2].values()) > 100000:
            raise TransferError("relation_limit", "关联数量超过 10 万条")
        check = importer.get_check_attr_map()
        identities = list(check["is_only"]) or ["inst_name"]
        attrs_by_id = {item["attr_id"]: item for item in attrs}
        summary = dict(created=0, updated=0, failed_rows=0, created_relations=0, failed_relations=0)
        errors, relations, seen = [], [], set()
        successful = {}
        for offset in range(0, len(rows), 200):
            progress(offset, len(rows), summary, "matching")
            context = TransferAuthorization.revalidate(task)
            batch = rows[offset : offset + 200]
            matches, candidates = TransferImport._match_batch(task.model_id, identities, attrs, batch, progress, offset, summary, len(rows))
            for index, (number, item, row_relations, error) in enumerate(batch, offset + 1):
                progress(index - 1, len(rows), summary, "writing_instances")
                item.setdefault("organization", [task.team_id])
                if error:
                    for column, field_id, reason in error:
                        errors.append((number, column, field_id, TransferImport._public_reason(field_id, reason)))
                    summary["failed_rows"] += 1
                    progress(index, len(rows), summary, "writing_instances")
                    continue
                identity = TransferImport._identity_fingerprint(identities, attrs_by_id, item)
                existing = matches.get(identity, [])
                row_problems = []
                if identity in seen or len(existing) > 1:
                    row_problems.append((identities[0], "文件内标识重复或匹配到多个已有实例"))
                seen.add(identity)
                row_problems.extend((field, "缺少实例唯一标识") for field in identities if item.get(field) in (None, ""))
                row_problems.extend(
                    (field, f"缺少必填字段「{name}」")
                    for field, name in check["is_required"].items()
                    if item.get(field) in (None, "", []) and not (existing and existing[0].get(field))
                )
                for field_error in FieldValidator.validate_instance_data(item, attrs):
                    row_problems.append((field_error.get("field") or "", field_error.get("error") or "字段值不符合模型校验规则"))
                if not isinstance(item["organization"], list) or not set(item["organization"]).issubset(context.teams):
                    row_problems.append(("organization", "目标组织不在授权范围内"))
                before = existing[0] if len(existing) == 1 else None
                try:
                    if before:
                        TransferAuthorization.check_instance(context, before, write=True)
                    else:
                        TransferAuthorization.check_instance(context, item, write=True, require_edit=False)
                except TransferError:
                    row_problems.append(("organization", "没有该实例或目标组织的操作权限"))
                exclude_ids = {before["_id"]} if before and before.get("_id") is not None else set()
                for conflict in collect_instance_unique_conflicts(check, [item], candidates, exclude_instance_ids=exclude_ids):
                    row_problems.append((conflict.field_ids[0] if conflict.field_ids else identities[0], conflict.message))
                if row_problems:
                    for field_id, reason in row_problems:
                        TransferImport._record(errors, number, importer, field_id, reason)
                    summary["failed_rows"] += 1
                    progress(index, len(rows), summary, "writing_instances")
                    continue
                result, unique_failure = TransferImport._execute_instance_write(task, context, check, before, item, number)
                if unique_failure:
                    TransferImport._record(errors, number, importer, unique_failure[0], unique_failure[1])
                    summary["failed_rows"] += 1
                    progress(index, len(rows), summary, "writing_instances")
                    continue
                summary["updated" if before else "created"] += 1
                successful[number] = result
                candidates.append(result)
                relations.extend((number, key, name) for key, names in row_relations.items() for name in names)
                progress(index, len(rows), summary, "writing_instances")
        TransferImport._write_relations(task, context, importer, relations, successful, summary, errors, progress, len(rows))
        return summary, errors

    @staticmethod
    def _write_relations(task, context, importer, relations, successful, summary, errors, progress, total):
        association_map = {item["model_asst_id"]: item for item in context.associations}
        for number, key, name in relations:
            progress(total, total, summary, "writing_relations")
            context = TransferAuthorization.revalidate(task)
            definition = association_map[key]
            source = successful[number]
            source_is_src = definition["src_model_id"] == task.model_id
            peer_model = definition["dst_model_id" if source_is_src else "src_model_id"]
            try:
                peer_context = TransferAuthorization.resolve(task.owner, task.team_id, task.include_children, peer_model, "export")
                with GraphClient() as graph:
                    peers, _ = graph.query_entity(
                        INSTANCE,
                        [{"field": "model_id", "type": "str=", "value": peer_model}, {"field": "inst_name", "type": "str=", "value": name}],
                        page={"skip": 0, "limit": 2},
                        include_count=False,
                    )
                if len(peers) != 1:
                    raise TransferError("invalid_relation", "关联目标不存在或名称不唯一")
                TransferAuthorization.check_instance(context, source, write=True)
                TransferAuthorization.check_instance(peer_context, peers[0], write=True)
            except TransferError:
                TransferImport._record(errors, number, importer, key, "关联目标不存在、不唯一或无操作权限")
                summary["failed_relations"] += 1
                continue
            src, dst = (source, peers[0]) if source_is_src else (peers[0], source)
            try:
                result = InstanceManage.instance_association_create_by_uuid(
                    src_inst_uuid=src["inst_uuid"],
                    dst_inst_uuid=dst["inst_uuid"],
                    model_asst_id=key,
                    operator=context.actor.username,
                    bounded_lookup=True,
                    allow_existing=True,
                )
            except BaseAppException as exc:
                if exc.message in ("instance association repetition", "edge already exists"):
                    summary["existing_relations"] = summary.get("existing_relations", 0) + 1
                    progress(total, total, summary, "writing_relations")
                    continue
                if exc.message in (
                    "实例不存在！",
                    "association not found!",
                    "source instance already exists association!",
                    "destination instance already exists association!",
                ):
                    TransferImport._record(errors, number, importer, key, "关联端点已变化或不满足关系数量约束")
                    summary["failed_relations"] += 1
                    continue
                raise  # 只处理已证明在写图前抛出的领域错误；未知写入结果不得猜测。
            if (result or {}).get("already_exists"):
                summary["existing_relations"] = summary.get("existing_relations", 0) + 1
            else:
                summary["created_relations"] += 1
            progress(total, total, summary, "writing_relations")
