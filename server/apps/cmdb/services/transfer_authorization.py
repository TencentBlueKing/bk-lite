from types import SimpleNamespace

from apps.cmdb.constants.constants import OPERATE, PERMISSION_INSTANCES, VIEW
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.model_visibility import BusinessModelVisibility
from apps.cmdb.services.transfer_service import TransferError, fingerprint
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.system_mgmt.nats.auth import build_user_authorization_context


class TransferAuthorization:
    @staticmethod
    def resolve(owner, team_id, include_children, model_id, kind):
        if owner.disabled:
            raise TransferError("owner_disabled", "用户已停用", 403)
        owner.group_list = [int(value.get("id") if isinstance(value, dict) else value) for value in owner.group_list]
        actor = SimpleNamespace(**build_user_authorization_context(owner))
        actions = actor.permission.get("cmdb", [])
        required = "asset_info-Add" if kind == "import" else "asset_info-View"
        if not actor.is_superuser and required not in actions:
            raise TransferError("permission_denied", "没有导入导出权限", 403)
        teams = CmdbRulesFormatUtil.get_authorized_team_ids(actor, team_id, include_children)
        if not teams:
            raise TransferError("permission_denied", "没有当前组织的访问权限", 403)
        permission_map = CmdbRulesFormatUtil.format_user_context_permissions(actor, team_id, include_children, model_id)
        # 不把每次随机生成的拒绝哨兵写入授权快照，也不能将其转为空映射（空映射代表全权）。
        permission_map = {
            key: value
            for key, value in permission_map.items()
            if not value["permission_instances_map"] or any(value["permission_instances_map"].values())
        }
        if not permission_map:
            raise TransferError("permission_denied", "当前范围没有实例权限", 403)
        model = BusinessModelVisibility.resolve([model_id]).get(model_id)
        if not model:
            raise TransferError("model_not_found", "模型不存在或不可见", 404)
        attrs = ModelManage.search_model_attr(model_id)
        associations = ModelManage.model_association_search(model_id, business_only=True)
        schema_attrs = []
        for attr in attrs:
            semantic = dict(attr)
            option = attr.get("option") or {}
            if attr.get("attr_type") == "tag" and option.get("mode", "free") == "free":
                # 自由标签的候选项由实例写入追加，不属于模板约束变化；严格模式候选项仍参与指纹。
                semantic["option"] = {key: value for key, value in option.items() if key != "options"}
            schema_attrs.append(semantic)
        schema_hash = fingerprint([schema_attrs, associations])
        snapshot = {
            "teams": sorted(teams),
            "permissions": {
                str(team): {
                    "inst_names": sorted(value["inst_names"]),
                    "permission_instances_map": {name: sorted(operations) for name, operations in value["permission_instances_map"].items()},
                }
                for team, value in permission_map.items()
            },
            "actions": sorted(actions),
            "admin": actor.is_superuser,
        }
        return SimpleNamespace(
            actor=actor,
            teams=teams,
            permission_map=permission_map,
            attrs=attrs,
            associations=associations,
            model=model,
            snapshot=snapshot,
            schema_hash=schema_hash,
            can_update=actor.is_superuser or "asset_info-Edit" in actions,
        )

    @staticmethod
    def validate_task(task, context):
        if task.authorization != context.snapshot:
            raise TransferError("authorization_changed", "权限范围已变化，请按当前权限重新提交", 403)
        if task.schema_hash != context.schema_hash:
            raise TransferError("schema_changed", "模型结构已变化，请重新下载模板或提交任务", 409)

    @classmethod
    def revalidate(cls, task):
        task.owner.refresh_from_db()
        context = cls.resolve(task.owner, task.team_id, task.include_children, task.model_id, task.kind)
        cls.validate_task(task, context)
        return context

    @staticmethod
    def check_instance(context, instance, *, write=False, require_edit=True):
        if write and require_edit and not context.can_update:
            raise TransferError("permission_denied", "没有实例编辑权限", 403)
        if not CmdbRulesFormatUtil.has_object_permission(
            PERMISSION_INSTANCES, OPERATE if write else VIEW, instance["model_id"], context.permission_map, instance
        ):
            raise TransferError("permission_denied", "实例不在授权范围内", 403)
