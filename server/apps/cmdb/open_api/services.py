from rest_framework.exceptions import ValidationError

from apps.cmdb.constants.constants import OPERATE, PERMISSION_INSTANCES, PERMISSION_MODEL, VIEW
from apps.cmdb.services.classification import ClassificationManage
from apps.cmdb.services.instance import InstanceBatchError, InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.utils.base import get_default_group_id
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.core.exceptions.base_app_exception import BaseAppException

from .errors import CMDBOpenAPIError
from .serializers import (
    BatchCreateSerializer,
    BatchDeleteSerializer,
    BatchUpdateSerializer,
    AssociationCreateSerializer,
    InstanceListQuerySerializer,
    validate_instance_payload,
)


def _raise_open_api_batch_error(exc: InstanceBatchError):
    error_contract = {
        "validation": ("cmdb.validation.failed", 400),
        "unique_conflict": ("cmdb.instance.unique_conflict", 409),
        "not_found": ("cmdb.instance.not_found", 404),
        "incomplete": ("cmdb.instance.batch_incomplete", 500),
    }
    code, status_code = error_contract.get(exc.reason, ("cmdb.request.failed", 500))
    raise CMDBOpenAPIError(code, exc.message, status_code, exc.data) from exc


def _organization_ids(instance):
    result = set()
    for item in instance.get("organization", []) or []:
        try:
            result.add(int(item))
        except (TypeError, ValueError):
            continue
    return result


def serialize_instance(instance):
    aliases = {
        "_id": "inst_id",
        "_creator": "creator",
        "_created_at": "created_at",
        "_updated_at": "updated_at",
    }
    hidden = {"_labels", "permission"}
    return {aliases.get(key, key): value for key, value in instance.items() if key not in hidden}


class CMDBOpenAPIService:
    def __init__(self, context):
        self.context = context

    def _model_permissions(self, model_id=""):
        permissions = self.context.permission_map(model_id, PERMISSION_MODEL)
        default_group_id = get_default_group_id()[0]
        permissions.setdefault(
            default_group_id,
            {"permission_instances_map": {}, "inst_names": [], "__default_model": [VIEW]},
        )
        return permissions

    def list_models(self):
        self.context.require_feature("model_management-View")
        return ModelManage.search_model(
            language=self.context.user.locale,
            permissions_map=self._model_permissions(),
            include_hidden=False,
        )

    def list_classifications(self):
        visible_ids = {item["classification_id"] for item in self.list_models()}
        rows = ClassificationManage.search_model_classification(
            self.context.user.locale,
            include_hidden=False,
        )
        return [row for row in rows if row.get("classification_id") in visible_ids]

    def get_model(self, model_id):
        self.context.require_feature("model_management-View")
        model = ModelManage.search_model_info(model_id)
        if not model:
            raise CMDBOpenAPIError("cmdb.model.not_found", "模型不存在", 404)
        if not CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=VIEW,
            model_id=model_id,
            permission_instances_map=self._model_permissions(model_id),
            instance=model,
            default_group_id=get_default_group_id()[0],
        ):
            raise CMDBOpenAPIError("cmdb.model.not_found", "模型不存在", 404)
        return model

    def get_model_attrs(self, model_id):
        self.get_model(model_id)
        return ModelManage.search_model_attr(model_id)

    def get_model_associations(self, model_id):
        self.get_model(model_id)
        return ModelManage.model_association_search(model_id)

    def _instance_permission_map(self, model_id):
        return self.context.permission_map(model_id, PERMISSION_INSTANCES)

    def _get_instance(self, model_id, inst_id, operator):
        instance = InstanceManage.query_entity_by_id(int(inst_id))
        if (
            not instance
            or instance.get("model_id") != model_id
            or self.context.team_id not in _organization_ids(instance)
        ):
            raise CMDBOpenAPIError("cmdb.instance.not_found", "实例不存在", 404)
        creator_allowed = instance.get("_creator") == self.context.user.username
        if not creator_allowed and not CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_INSTANCES,
            operator=operator,
            model_id=model_id,
            permission_instances_map=self._instance_permission_map(model_id),
            instance=instance,
        ):
            raise CMDBOpenAPIError("cmdb.permission.denied", "权限不足", 403)
        return instance

    def list_instances(self, model_id, query):
        self.context.require_feature("asset_info-View")
        attrs = self.get_model_attrs(model_id)
        serializer = InstanceListQuerySerializer(data=query, context={"attrs": attrs})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        instances, count = InstanceManage.instance_list(
            model_id=model_id,
            params=list(data["filters"]),
            page=data["page"],
            page_size=data["page_size"],
            order=data["order"],
            permission_map=self._instance_permission_map(model_id),
            creator=self.context.user.username,
        )
        return {
            "count": count,
            "page": data["page"],
            "page_size": data["page_size"],
            "items": [serialize_instance(instance) for instance in instances],
        }

    def create_instance(self, model_id, payload):
        self.context.require_feature("asset_info-Add")
        attrs = self.get_model_attrs(model_id)
        data = validate_instance_payload(
            payload,
            attrs,
            team_id=self.context.team_id,
            for_update=False,
        )
        result = InstanceManage.instance_create(
            model_id,
            data,
            self.context.user.username,
            allowed_org_ids=[self.context.team_id],
        )
        return serialize_instance(result)

    def update_instance(self, model_id, inst_id, payload):
        self.context.require_feature("asset_info-Edit")
        self._get_instance(model_id, inst_id, OPERATE)
        data = validate_instance_payload(
            payload,
            self.get_model_attrs(model_id),
            team_id=self.context.team_id,
            for_update=True,
        )
        result = InstanceManage.instance_update(
            self.context.user_groups,
            self.context.user.roles,
            int(inst_id),
            data,
            self.context.user.username,
            allowed_org_ids=[self.context.team_id],
        )
        return serialize_instance(result)

    def delete_instance(self, model_id, inst_id):
        self.context.require_feature("asset_info-Delete")
        self._get_instance(model_id, inst_id, OPERATE)
        InstanceManage.instance_batch_delete(
            self.context.user_groups,
            self.context.user.roles,
            [int(inst_id)],
            self.context.user.username,
        )
        return {"deleted": [int(inst_id)]}

    def list_instance_associations(self, model_id, inst_id):
        self.context.require_feature("asset_info-View")
        self._get_instance(model_id, inst_id, VIEW)
        return InstanceManage.instance_association_instance_list(model_id, int(inst_id))

    def create_instance_association(self, model_id, inst_id, payload):
        self.context.require_feature("asset_info-Add Associate")
        serializer = AssociationCreateSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self._get_instance(model_id, inst_id, OPERATE)
        self._get_instance(data["target_model_id"], data["target_inst_id"], OPERATE)
        association = ModelManage.model_association_info_search(data["model_asst_id"])
        if (
            not association
            or association.get("src_model_id") != model_id
            or association.get("dst_model_id") != data["target_model_id"]
        ):
            raise CMDBOpenAPIError("cmdb.association.invalid_direction", "关联方向非法", 400)
        try:
            edge = InstanceManage.instance_association_create(
                {
                    "src_inst_id": int(inst_id),
                    "dst_inst_id": data["target_inst_id"],
                    "model_asst_id": data["model_asst_id"],
                },
                self.context.user.username,
            )
        except BaseAppException as exc:
            if exc.message == "instance association repetition":
                raise CMDBOpenAPIError("cmdb.association.conflict", "关联关系已存在", 409) from exc
            raise
        return {"association_id": edge["_id"], "model_asst_id": data["model_asst_id"]}

    def delete_instance_association(self, model_id, inst_id, association_id):
        self.context.require_feature("asset_info-Delete Associate")
        association = InstanceManage.instance_association_by_asso_id(int(association_id))
        src = (association or {}).get("src") or {}
        if int(src.get("_id") or 0) != int(inst_id) or src.get("model_id") != model_id:
            raise CMDBOpenAPIError("cmdb.association.not_found", "关联关系不存在", 404)
        dst = (association or {}).get("dst") or {}
        try:
            dst_inst_id = int(dst.get("_id") or 0)
        except (TypeError, ValueError):
            dst_inst_id = 0
        dst_model_id = dst.get("model_id")
        if dst_inst_id <= 0 or not dst_model_id:
            raise CMDBOpenAPIError("cmdb.association.not_found", "关联关系不存在", 404)
        self._get_instance(model_id, inst_id, OPERATE)
        self._get_instance(dst_model_id, dst_inst_id, OPERATE)
        InstanceManage.instance_association_delete(int(association_id), self.context.user.username)
        return {"deleted": int(association_id)}

    def batch_create_instances(self, model_id, payload):
        self.context.require_feature("asset_info-Add")
        serializer = BatchCreateSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        attrs = self.get_model_attrs(model_id)
        items = []
        for index, item in enumerate(serializer.validated_data["items"]):
            try:
                items.append(
                    validate_instance_payload(
                        item,
                        attrs,
                        team_id=self.context.team_id,
                        for_update=False,
                    )
                )
            except ValidationError as exc:
                raise CMDBOpenAPIError(
                    "cmdb.validation.failed",
                    "请求参数非法",
                    400,
                    {"index": index},
                ) from exc

        try:
            created = InstanceManage.instance_batch_create(
                model_id,
                items,
                self.context.user.username,
                [self.context.team_id],
            )
        except InstanceBatchError as exc:
            _raise_open_api_batch_error(exc)
        return {"created": [serialize_instance(item) for item in created]}

    def batch_update_instances(self, model_id, payload):
        self.context.require_feature("asset_info-Edit")
        serializer = BatchUpdateSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        inst_ids = list(dict.fromkeys(serializer.validated_data["inst_ids"]))
        for inst_id in inst_ids:
            try:
                self._get_instance(model_id, inst_id, OPERATE)
            except CMDBOpenAPIError as exc:
                raise CMDBOpenAPIError(
                    exc.code,
                    exc.message,
                    exc.status_code,
                    {**exc.data, "inst_id": inst_id},
                ) from exc

        update_data = validate_instance_payload(
            serializer.validated_data["update_data"],
            self.get_model_attrs(model_id),
            team_id=self.context.team_id,
            for_update=True,
        )
        try:
            updated = InstanceManage.batch_instance_update(
                self.context.user_groups,
                self.context.user.roles,
                inst_ids,
                update_data,
                self.context.user.username,
                [self.context.team_id],
            )
        except InstanceBatchError as exc:
            _raise_open_api_batch_error(exc)
        return {"updated": [serialize_instance(item) for item in updated]}

    def batch_delete_instances(self, model_id, payload):
        self.context.require_feature("asset_info-Delete")
        serializer = BatchDeleteSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        inst_ids = list(dict.fromkeys(serializer.validated_data["inst_ids"]))
        for inst_id in inst_ids:
            try:
                self._get_instance(model_id, inst_id, OPERATE)
            except CMDBOpenAPIError as exc:
                raise CMDBOpenAPIError(
                    exc.code,
                    exc.message,
                    exc.status_code,
                    {**exc.data, "inst_id": inst_id},
                ) from exc

        try:
            InstanceManage.instance_batch_delete(
                self.context.user_groups,
                self.context.user.roles,
                inst_ids,
                self.context.user.username,
            )
        except InstanceBatchError as exc:
            _raise_open_api_batch_error(exc)
        return {"deleted": inst_ids}
