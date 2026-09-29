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
    def _load_unique_conflict_candidates(model_id, identities, attrs, batch, candidates, seen_ids):
        """按单个唯一字段补齐冲突候选。查不到或超上限时不阻断导入，写入期再兜底。"""
        for field in identities:
            values = list({row[1][field] for row in batch if row[1].get(field) is not None})
            if not values:
                continue
            attr = next((item for item in attrs if item["attr_id"] == field), {})
            cursor = None
            while len(candidates) < 5000:
                page_params = [
                    {"field": "model_id", "type": "str=", "value": model_id},
                    {"field": field, "type": "int[]" if attr.get("attr_type") == "int" else "str[]", "value": values},
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
        params = [{"field": "model_id", "type": "str=", "value": model_id}]
        for field in identities:
            values = list({row[1][field] for row in batch if row[1].get(field) is not None})
            attr = next((item for item in attrs if item["attr_id"] == field), {})
            params.append({"field": field, "type": "int[]" if attr.get("attr_type") == "int" else "str[]", "value": values})
        matches = defaultdict(list)
        candidates = []
        seen_ids = set()
        combo_matched = False
        if all(param["value"] for param in params):
            combo_matched = True
            cursor = None
            while True:
                page_params = params + ([{"field": "inst_uuid", "type": "str>", "value": cursor}] if cursor else [])
                with GraphClient() as graph:
                    found, _ = graph.query_entity(INSTANCE, page_params, page={"skip": 0, "limit": 500}, order="inst_uuid", include_count=False)
                for existing in found:
                    matches[fingerprint([existing.get(field) for field in identities])].append(existing)
                    key = existing.get("_id", existing.get("inst_uuid"))
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
                identity = fingerprint([item.get(field) for field in identities])
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
