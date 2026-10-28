# -- coding: utf-8 --
"""按目标画布 id 覆盖定义。

认人只看调用方给出的画布主键，不读取 YAML 里的名称做匹配，也不走目录导入的
skip/rename/overwrite 冲突页。已有数据源复用且不改定义；缺失的数据源和命名空间
才创建，新建数据源的组织跟随当前画布。
"""

from django.db import transaction

from apps.operation_analysis.constants.import_export import SENSITIVE_PLACEHOLDER, ConflictAction, ImportExportErrorCode, ImportStatus, ObjectType
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace
from apps.operation_analysis.schemas.import_export_schema import YAMLDocument, validate_date_range_params
from apps.operation_analysis.services.canvas.registry import CANVAS_TYPE_REGISTRY
from apps.operation_analysis.services.import_export.import_service import ImportService
from apps.operation_analysis.services.import_export.precheck_service import PrecheckService
from apps.operation_analysis.services.user_messages import oa_message


class CanvasImportUpdateService:
    @staticmethod
    def object_type_for(canvas) -> ObjectType:
        for object_type, meta in CANVAS_TYPE_REGISTRY.items():
            if isinstance(canvas, meta.model):
                return ObjectType(object_type)
        raise ValueError(oa_message("messages.import_update_target_missing", "目标画布不存在或已删除"))

    @classmethod
    def apply(cls, *, canvas, yaml_content: str, updated_by: str = "") -> dict:
        object_type = cls.object_type_for(canvas)
        prepared = cls.prepare(canvas, object_type, yaml_content)
        if not prepared["valid"]:
            return {
                "success": False,
                "errors": prepared["errors"],
                "message": prepared["message"],
                "object_type": object_type.value,
            }
        return cls._execute(
            canvas=canvas,
            object_type=object_type,
            doc=prepared["doc"],
            canvas_item=prepared["canvas_item"],
            updated_by=updated_by,
        )

    @classmethod
    def prepare(cls, canvas, object_type: ObjectType, yaml_content: str) -> dict:
        errors = cls._structural_errors(yaml_content)
        if errors:
            return cls._invalid(errors)

        data, parse_errors = PrecheckService.parse_yaml(yaml_content)
        errors.extend(parse_errors)
        if errors or data is None:
            return cls._invalid(errors)

        doc, schema_errors = PrecheckService.validate_schema(data)
        errors.extend(schema_errors)
        if errors or doc is None:
            return cls._invalid(errors)

        errors.extend(PrecheckService.check_object_counts_consistency(doc))
        errors.extend(PrecheckService.check_object_limit(doc))
        if errors:
            return cls._invalid(errors)

        meta = CANVAS_TYPE_REGISTRY[object_type.value]
        canvases = list(getattr(doc, meta.section_name) or [])
        if len(canvases) == 0:
            errors.append(
                {
                    "code": ImportExportErrorCode.IMPORT_UPDATE_TYPE_MISMATCH,
                    "message": oa_message(
                        "messages.import_update_type_mismatch",
                        "YAML 中没有与当前画布类型 {object_type} 一致的画布",
                        object_type=object_type.value,
                    ),
                    "object_type": object_type.value,
                }
            )
            return cls._invalid(errors)
        if len(canvases) != 1:
            errors.append(
                {
                    "code": ImportExportErrorCode.IMPORT_UPDATE_CANVAS_COUNT,
                    "message": oa_message(
                        "messages.import_update_canvas_count",
                        "YAML 中有 {count} 个 {object_type}，导入更新要求恰好 1 个",
                        count=len(canvases),
                        object_type=object_type.value,
                    ),
                    "object_type": object_type.value,
                }
            )
            return cls._invalid(errors)

        canvas_item = canvases[0]
        datasources, namespaces = cls._dependency_closure(doc, canvas_item)
        narrowed = doc.model_copy(
            update={
                **{item.section_name: [] for item in CANVAS_TYPE_REGISTRY.values()},
                meta.section_name: [canvas_item],
                "datasources": datasources,
                "namespaces": namespaces,
            }
        )

        for violation in validate_date_range_params(narrowed):
            errors.append(
                {
                    "code": ImportExportErrorCode.YAML_SCHEMA_INVALID,
                    "message": oa_message(
                        "messages.field_invalid",
                        "字段 '{loc}' 值无效: {detail}",
                        loc=violation["path"],
                        detail=violation["message"],
                    ),
                    "details": violation,
                }
            )
        errors.extend(PrecheckService.check_db_id_references(narrowed.model_dump()))
        errors.extend(PrecheckService.check_dependencies(narrowed))
        if errors:
            return cls._invalid(errors)

        if getattr(canvas, "is_build_in", False):
            errors.append(cls._builtin_error())
            return cls._invalid(errors)

        errors.extend(cls._name_conflict_errors(meta.model, canvas, canvas_item, object_type))
        errors.extend(cls._dependency_ready_errors(namespaces, datasources))
        if errors:
            return cls._invalid(errors)

        return {
            "valid": True,
            "errors": [],
            "message": "",
            "doc": narrowed,
            "canvas_item": canvas_item,
        }

    @classmethod
    @transaction.atomic
    def _execute(cls, *, canvas, object_type: ObjectType, doc: YAMLDocument, canvas_item, updated_by: str) -> dict:
        meta = CANVAS_TYPE_REGISTRY[object_type.value]
        locked = meta.model.objects.select_for_update().filter(pk=canvas.pk).first()
        if locked is None:
            return cls._failure([cls._target_missing_error()], object_type)
        if getattr(locked, "is_build_in", False):
            return cls._failure([cls._builtin_error()], object_type)

        name_errors = cls._name_conflict_errors(meta.model, locked, canvas_item, object_type)
        if name_errors:
            return cls._failure(name_errors, object_type)

        ready_errors = cls._dependency_ready_errors(doc.namespaces, doc.datasources)
        if ready_errors:
            return cls._failure(ready_errors, object_type)

        datasource_groups = list(locked.groups or [])
        decisions_by_type = {(ObjectType.NAMESPACE.value, item.key): ConflictAction.SKIP.value for item in doc.namespaces}
        decisions_by_type.update({(ObjectType.DATASOURCE.value, item.key): ConflictAction.SKIP.value for item in doc.datasources})
        decisions_by_type[(object_type.value, canvas_item.key)] = ConflictAction.OVERWRITE.value
        result = ImportService(
            doc=doc,
            target_directory_id=locked.directory_id,
            conflict_decisions={},
            conflict_decisions_by_type=decisions_by_type,
            secret_supplements={},
            created_by=updated_by,
            updated_by=updated_by,
            groups=datasource_groups,
            datasource_groups=datasource_groups,
            existing_canvas_ids={(object_type.value, canvas_item.key): locked.pk},
            preserve_existing_canvas_groups=True,
        ).execute()
        if not result.get("success"):
            return cls._failure(cls._errors_from_import_results(result.get("results") or []), object_type)

        locked.refresh_from_db()
        return {
            "success": True,
            "errors": [],
            "message": "",
            "object_type": object_type.value,
            "canvas_id": locked.pk,
            "name": locked.name,
            "desc": locked.desc or "",
            "summary": result.get("summary") or {},
            "results": result.get("results") or [],
        }

    @staticmethod
    def _errors_from_import_results(results: list[dict]) -> list[dict]:
        failed = [item for item in results if item.get("status") == ImportStatus.FAILED.value]
        errors = [CanvasImportUpdateService._error_from_import_result(item) for item in failed]
        if errors:
            return errors
        return [
            {
                "code": ImportExportErrorCode.IMPORT_DEPENDENCY_MISSING,
                "message": oa_message("messages.precheck_failed", "预检失败，无法执行导入"),
            }
        ]

    @staticmethod
    def _error_from_import_result(item: dict) -> dict:
        code = item.get("code")
        if not code:
            code = (
                ImportExportErrorCode.IMPORT_SECRET_REQUIRED
                if CanvasImportUpdateService._message_is_missing_secret(item.get("message") or "")
                else ImportExportErrorCode.IMPORT_DEPENDENCY_MISSING
            )
        return {
            "code": code,
            "message": item.get("message") or oa_message("messages.precheck_failed", "预检失败，无法执行导入"),
            "object_key": item.get("object_key"),
        }

    @staticmethod
    def _message_is_missing_secret(message: str) -> bool:
        markers = (
            oa_message("messages.import_namespace_password_missing", "新建命名空间缺少密码"),
            "缺少敏感配置",
            "missing sensitive settings",
        )
        return any(marker and marker in message for marker in markers)

    @staticmethod
    def _structural_errors(yaml_content: str) -> list[dict]:
        return list(PrecheckService.check_size_threshold(yaml_content))

    @staticmethod
    def _dependency_closure(doc: YAMLDocument, canvas_item):
        datasource_keys = set(getattr(canvas_item.refs, "datasource_keys", None) or [])
        namespace_keys = set(getattr(canvas_item.refs, "namespace_keys", None) or [])
        datasources = [item for item in doc.datasources if item.key in datasource_keys]
        for item in datasources:
            namespace_keys.update(item.namespace_keys or [])
        namespaces = [item for item in doc.namespaces if item.key in namespace_keys]
        return datasources, namespaces

    @staticmethod
    def _name_conflict_errors(model, canvas, canvas_item, object_type: ObjectType) -> list[dict]:
        if not model.objects.filter(name=canvas_item.name).exclude(pk=canvas.pk).exists():
            return []
        return [
            {
                "code": ImportExportErrorCode.IMPORT_UPDATE_NAME_TAKEN,
                "message": oa_message(
                    "messages.import_update_name_taken",
                    "名称「{name}」已被其他{object_type}占用",
                    name=canvas_item.name,
                    object_type=object_type.value,
                ),
                "object_type": object_type.value,
            }
        ]

    @classmethod
    def _dependency_ready_errors(cls, namespaces, datasources) -> list[dict]:
        errors = []
        existing_namespace_names = set(NameSpace.objects.filter(name__in=[item.name for item in namespaces]).values_list("name", flat=True))
        for item in namespaces:
            if item.name in existing_namespace_names:
                continue
            password = item.password or ""
            if not password or password == SENSITIVE_PLACEHOLDER:
                errors.append(
                    {
                        "code": ImportExportErrorCode.IMPORT_SECRET_REQUIRED,
                        "message": oa_message("messages.import_namespace_password_missing", "新建命名空间缺少密码"),
                        "object_key": item.key,
                        "object_type": ObjectType.NAMESPACE.value,
                    }
                )

        existing_datasources = {(row.name, row.rest_api) for row in DataSourceAPIModel.objects.filter(name__in=[item.name for item in datasources])}
        probe = ImportService(
            doc=YAMLDocument(),
            target_directory_id=None,
            conflict_decisions={},
            secret_supplements={},
        )
        for item in datasources:
            if (item.name, item.rest_api) in existing_datasources:
                continue
            legacy_errors = [
                error for error in PrecheckService.check_datasource_security(YAMLDocument(datasources=[item])) if error.get("object_key") == item.key
            ]
            if legacy_errors:
                errors.extend(legacy_errors)
                continue
            _, _, missing = probe._prepare_datasource_configs(item)
            if missing:
                errors.append(
                    {
                        "code": ImportExportErrorCode.IMPORT_SECRET_REQUIRED,
                        "message": oa_message(
                            "messages.import_datasource_secrets_missing",
                            "数据源缺少敏感配置: {fields}",
                            fields=", ".join(missing),
                        ),
                        "object_key": item.key,
                        "object_type": ObjectType.DATASOURCE.value,
                    }
                )
        return errors

    @staticmethod
    def _builtin_error() -> dict:
        return {
            "code": ImportExportErrorCode.IMPORT_UPDATE_BUILTIN,
            "message": oa_message("messages.import_update_builtin", "内置画布不允许导入更新"),
        }

    @staticmethod
    def _target_missing_error() -> dict:
        return {
            "code": ImportExportErrorCode.IMPORT_UPDATE_TARGET_MISSING,
            "message": oa_message("messages.import_update_target_missing", "目标画布不存在或已删除"),
        }

    @classmethod
    def _invalid(cls, errors: list[dict]) -> dict:
        failure = cls._failure(errors, None)
        failure.pop("object_type", None)
        return failure

    @staticmethod
    def _failure(errors: list[dict], object_type: ObjectType | None) -> dict:
        message = "；".join(error.get("message") or "" for error in errors if error.get("message"))
        if not message:
            message = oa_message("messages.precheck_failed", "预检失败，无法执行导入")
        payload = {"success": False, "valid": False, "errors": errors, "message": message}
        if object_type is not None:
            payload["object_type"] = object_type.value
        return payload
