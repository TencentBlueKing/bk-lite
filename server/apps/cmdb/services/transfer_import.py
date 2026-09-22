from collections import defaultdict

from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.change_record_snapshot import load_attribute_snapshot
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.operation_service import OperationService
from apps.cmdb.services.transfer_authorization import TransferAuthorization
from apps.cmdb.services.transfer_service import TransferError, fingerprint
from apps.cmdb.utils.Import import Import
from apps.cmdb.validators import FieldValidator
from apps.core.exceptions.base_app_exception import BaseAppException


class TransferImport:
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
            context = TransferAuthorization.revalidate(task)
            batch = rows[offset : offset + 200]
            # 按本批唯一标识过滤候选，不读取整个模型；组合值在内存做精确匹配。
            params = [{"field": "model_id", "type": "str=", "value": task.model_id}]
            for field in identities:
                values = list({row[1][field] for row in batch if row[1].get(field) is not None})
                attr = next((item for item in attrs if item["attr_id"] == field), {})
                params.append({"field": field, "type": "int[]" if attr.get("attr_type") == "int" else "str[]", "value": values})
            matches = defaultdict(list)
            if all(param["value"] for param in params):
                cursor = None
                while True:
                    page_params = params + ([{"field": "inst_uuid", "type": "str>", "value": cursor}] if cursor else [])
                    with GraphClient() as graph:
                        found, _ = graph.query_entity(INSTANCE, page_params, page={"skip": 0, "limit": 500}, order="inst_uuid", include_count=False)
                    for existing in found:
                        matches[fingerprint([existing.get(field) for field in identities])].append(existing)
                    if sum(map(len, matches.values())) > 10000:
                        raise TransferError("ambiguous_identity", "匹配到过多重复标识，请先清理实例唯一性")
                    if len(found) < 500:
                        break
                    cursor = found[-1]["inst_uuid"]
                    progress(offset, len(rows), summary, "matching")
            for index, (number, item, row_relations, error) in enumerate(batch, offset + 1):
                progress(index - 1, len(rows), summary, "writing_instances")
                item.setdefault("organization", [task.team_id])
                identity = fingerprint([item.get(field) for field in identities])
                existing = matches.get(identity, [])
                if identity in seen or len(existing) > 1:
                    error = "文件内标识重复或匹配到多个已有实例"
                seen.add(identity)
                if any(item.get(field) in (None, "") for field in identities):
                    error = "缺少实例唯一标识"
                if any(item.get(field) in (None, "", []) and not (existing and existing[0].get(field)) for field in check["is_required"]):
                    error = "缺少模型必填字段"
                if FieldValidator.validate_instance_data(item, attrs):
                    error = "字段值不符合模型校验规则"
                if not isinstance(item["organization"], list) or not set(item["organization"]).issubset(context.teams):
                    error = "目标组织不在授权范围内"
                before = existing[0] if len(existing) == 1 else None
                try:
                    if before:
                        TransferAuthorization.check_instance(context, before, write=True)
                    else:
                        TransferAuthorization.check_instance(context, item, write=True, require_edit=False)
                except TransferError:
                    error = "没有该实例或目标组织的操作权限"
                if error:
                    errors.append((number, "instance", error))
                    summary["failed_rows"] += 1
                    progress(index, len(rows), summary, "writing_instances")
                    continue
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

                # 从此边界起任何异常都可能已有写入，由任务边界置为待核对，绝不猜测失败后继续/重放。
                def write(operation_id):
                    common = dict(allowed_org_ids=context.teams, record_change=False, operation_id=operation_id, schedule_post_actions=False)
                    if before:
                        return InstanceManage.instance_update_by_uuid(
                            context.teams, context.actor.roles, before["inst_uuid"], data, context.actor.username, **common
                        )
                    return InstanceManage.instance_create(task.model_id, data, context.actor.username, **common)

                result = OperationService.execute_graph(operation, graph_write=write, events=OperationService.events_for_operation(operation))
                summary["updated" if before else "created"] += 1
                successful[number] = result
                relations.extend((number, key, name) for key, names in row_relations.items() for name in names)
                progress(index, len(rows), summary, "writing_instances")
        TransferImport._write_relations(task, context, relations, successful, summary, errors, progress, len(rows))
        return summary, errors

    @staticmethod
    def _write_relations(task, context, relations, successful, summary, errors, progress, total):
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
                errors.append((number, "relation", "关联目标不存在、不唯一或无操作权限"))
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
                    errors.append((number, "relation", "关联端点已变化或不满足关系数量约束"))
                    summary["failed_relations"] += 1
                    continue
                raise  # 只处理已证明在写图前抛出的领域错误；未知写入结果不得猜测。
            if (result or {}).get("already_exists"):
                summary["existing_relations"] = summary.get("existing_relations", 0) + 1
            else:
                summary["created_relations"] += 1
            progress(total, total, summary, "writing_relations")
