# -- coding: utf-8 --
"""
YAML导入预检服务

负责在导入执行前进行全面校验，包括：
- YAML大小与对象数量阈值检查
- schema结构校验
- 非法数据库ID引用检测
- 业务键唯一性校验
- 依赖完整性校验
- 目标环境冲突识别
"""

import yaml
from pydantic import ValidationError

from apps.operation_analysis.constants.import_export import (
    CANVAS_TYPES,
    IMPORT_OBJECT_LIMIT,
    OBJECT_TYPE_TO_SECTION,
    SENSITIVE_FIELDS,
    SENSITIVE_PLACEHOLDER,
    YAML_MAX_SIZE_BYTES,
    ConflictAction,
    ConflictReason,
    ImportExportErrorCode,
    ImportExportWarningCode,
    ObjectType,
)
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace
from apps.operation_analysis.models.models import Architecture, Dashboard, NetworkTopology, Report, Screen, Topology
from apps.operation_analysis.schemas.import_export_schema import ImportExportValidationError, YAMLDocument, count_objects, detect_db_id_references


class PrecheckService:
    """
    YAML导入预检服务

    遵循Tech Plan 5.2节预检流程：
    1. 检查阈值
    2. YAML解析
    3. schema_version与章节结构校验
    4. 非法DB ID引用扫描
    5. 业务键唯一性校验
    6. 依赖完整性校验
    7. 冲突识别
    8. 生成 counts/conflicts/warnings/errors
    """

    MODEL_MAP = {
        ObjectType.DASHBOARD: Dashboard,
        ObjectType.TOPOLOGY: Topology,
        ObjectType.ARCHITECTURE: Architecture,
        ObjectType.SCREEN: Screen,
        ObjectType.REPORT: Report,
        ObjectType.NETWORK_TOPOLOGY: NetworkTopology,
        ObjectType.DATASOURCE: DataSourceAPIModel,
        ObjectType.NAMESPACE: NameSpace,
    }

    @staticmethod
    def check_size_threshold(yaml_content: str) -> list[dict]:
        """检查YAML内容大小是否超过阈值"""
        errors = []
        content_size = len(yaml_content.encode("utf-8"))
        if content_size > YAML_MAX_SIZE_BYTES:
            errors.append(
                {
                    "code": ImportExportErrorCode.YAML_TOO_LARGE,
                    "message": f"YAML大小 {content_size} 字节，超过 {YAML_MAX_SIZE_BYTES} 字节限制",
                }
            )
        return errors

    @staticmethod
    def parse_yaml(yaml_content: str) -> tuple[dict | None, list[dict]]:
        """解析YAML内容，返回解析结果和错误列表"""
        errors = []
        try:
            data = yaml.safe_load(yaml_content)
            if not isinstance(data, dict):
                errors.append(
                    {
                        "code": ImportExportErrorCode.YAML_PARSE_ERROR,
                        "message": "YAML内容必须是对象结构",
                    }
                )
                return None, errors
            return data, errors
        except yaml.YAMLError as e:
            errors.append(
                {
                    "code": ImportExportErrorCode.YAML_PARSE_ERROR,
                    "message": f"YAML语法错误: {str(e)}",
                }
            )
            return None, errors

    @staticmethod
    def _format_pydantic_error(e: ValidationError) -> str:
        """将Pydantic校验错误格式化为用户友好的消息"""
        error_messages = []
        for error in e.errors():
            loc = ".".join(str(x) for x in error["loc"])
            msg = error["msg"]
            error_type = error["type"]

            # 常见错误类型的友好提示
            if error_type == "dict_type":
                friendly_msg = f"字段 '{loc}' 应为对象(dict)类型"
            elif error_type == "list_type":
                friendly_msg = f"字段 '{loc}' 应为列表(list)类型"
            elif error_type == "string_type":
                friendly_msg = f"字段 '{loc}' 应为字符串类型"
            elif error_type == "int_type":
                friendly_msg = f"字段 '{loc}' 应为整数类型"
            elif error_type == "bool_type":
                friendly_msg = f"字段 '{loc}' 应为布尔类型"
            elif error_type == "missing":
                friendly_msg = f"缺少必填字段 '{loc}'"
            elif "value_error" in error_type:
                friendly_msg = f"字段 '{loc}' 值无效: {msg}"
            else:
                friendly_msg = f"字段 '{loc}' 校验失败: {msg}"

            error_messages.append(friendly_msg)

        return "; ".join(error_messages[:3])  # 最多显示3个错误

    @staticmethod
    def validate_schema(data: dict) -> tuple[YAMLDocument | None, list[dict]]:
        """使用Pydantic校验YAML结构"""
        errors = []
        try:
            doc = YAMLDocument(**data)
            return doc, errors
        except ValidationError as e:
            errors.append(
                {
                    "code": ImportExportErrorCode.YAML_SCHEMA_INVALID,
                    "message": f"YAML结构校验失败: {PrecheckService._format_pydantic_error(e)}",
                }
            )
            return None, errors
        except ImportExportValidationError as e:
            errors.append(
                {
                    "code": e.code,
                    "message": e.message,
                }
            )
            return None, errors

    @staticmethod
    def check_object_limit(doc: YAMLDocument) -> list[dict]:
        """检查对象数量是否超过阈值"""
        errors = []
        counts = count_objects(doc)
        if counts["total"] > IMPORT_OBJECT_LIMIT:
            errors.append(
                {
                    "code": ImportExportErrorCode.IMPORT_OBJECT_LIMIT_EXCEEDED,
                    "message": f"对象总数 {counts['total']} 超过 {IMPORT_OBJECT_LIMIT} 限制",
                }
            )
        return errors

    @staticmethod
    def check_object_counts_consistency(doc: YAMLDocument) -> list[dict]:
        errors = []
        actual_counts = count_objects(doc)["by_type"]
        declared_counts = doc.meta.object_counts or {}

        for object_type in [item.value for item in (*CANVAS_TYPES, ObjectType.DATASOURCE, ObjectType.NAMESPACE)]:
            section_name = OBJECT_TYPE_TO_SECTION[ObjectType(object_type)]
            declared = declared_counts.get(section_name, declared_counts.get(object_type, 0))
            actual = actual_counts.get(object_type, 0)
            if declared != actual:
                errors.append(
                    {
                        "code": ImportExportErrorCode.YAML_OBJECT_COUNTS_MISMATCH,
                        "message": f"meta.object_counts.{section_name} = {declared}，但实际对象数为 {actual}",
                        "object_type": object_type,
                    }
                )

        return errors

    @staticmethod
    def check_empty_import(doc: YAMLDocument) -> list[dict]:
        counts = count_objects(doc)
        if counts["total"] == 0:
            return [
                {
                    "code": ImportExportErrorCode.YAML_EMPTY_IMPORT,
                    "message": "YAML中没有可导入对象",
                }
            ]
        return []

    @staticmethod
    def check_db_id_references(data: dict) -> list[dict]:
        """检测非法数据库ID引用"""
        errors = []
        violations = detect_db_id_references(data)
        for v in violations:
            errors.append(
                {
                    "code": ImportExportErrorCode.YAML_ID_REFERENCE_FORBIDDEN,
                    "message": f"检测到非法DB ID引用: {v['path']} = {v['value']}",
                    "details": v,
                }
            )
        return errors

    @staticmethod
    def check_sensitive_placeholders(doc: YAMLDocument) -> list[dict]:
        """检查敏感字段占位符，生成警告"""
        warnings = []

        for ns in doc.namespaces:
            for field in SENSITIVE_FIELDS:
                value = getattr(ns, field, None)
                if value == SENSITIVE_PLACEHOLDER:
                    warnings.append(
                        {
                            "code": ImportExportWarningCode.SECRET_PLACEHOLDER,
                            "message": f"命名空间 '{ns.name}' 的 {field} 字段需要补充",
                            "object_key": ns.key,
                            "field": field,
                        }
                    )

        for network_topology in doc.network_topologies:
            if network_topology.token == SENSITIVE_PLACEHOLDER:
                warnings.append(
                    {
                        "code": ImportExportWarningCode.SECRET_PLACEHOLDER,
                        "message": f"网络拓扑 '{network_topology.name}' 的 token 字段需要补充",
                        "object_key": network_topology.key,
                        "field": "token",
                    }
                )

        return warnings

    @staticmethod
    def check_dependencies(doc: YAMLDocument) -> list[dict]:
        """检查依赖完整性：画布引用的数据源和命名空间是否在YAML中声明"""
        errors = []

        # 收集YAML中声明的命名空间和数据源键
        declared_ns_keys = {ns.key for ns in doc.namespaces}
        declared_ds_keys = {ds.key for ds in doc.datasources}

        # 检查数据源依赖的命名空间
        for ds in doc.datasources:
            for ns_key in ds.namespace_keys:
                if ns_key not in declared_ns_keys:
                    errors.append(
                        {
                            "code": ImportExportErrorCode.IMPORT_DEPENDENCY_MISSING,
                            "message": f"数据源 '{ds.name}' 依赖的命名空间 '{ns_key}' 未在YAML中声明",
                            "object_key": ds.key,
                            "missing_dependency": ns_key,
                        }
                    )

        # 检查画布依赖的数据源和命名空间
        all_canvases = [
            (doc.dashboards, ObjectType.DASHBOARD),
            (doc.topologies, ObjectType.TOPOLOGY),
            (doc.architectures, ObjectType.ARCHITECTURE),
            (doc.screens, ObjectType.SCREEN),
            (doc.reports, ObjectType.REPORT),
            (doc.network_topologies, ObjectType.NETWORK_TOPOLOGY),
        ]

        for canvas_list, obj_type in all_canvases:
            for canvas in canvas_list:
                for ds_key in canvas.refs.datasource_keys:
                    if ds_key not in declared_ds_keys:
                        errors.append(
                            {
                                "code": ImportExportErrorCode.IMPORT_DEPENDENCY_MISSING,
                                "message": f"{obj_type.value} '{canvas.name}' 依赖的数据源 '{ds_key}' 未在YAML中声明",
                                "object_key": canvas.key,
                                "missing_dependency": ds_key,
                            }
                        )

                for ns_key in canvas.refs.namespace_keys:
                    if ns_key not in declared_ns_keys:
                        errors.append(
                            {
                                "code": ImportExportErrorCode.IMPORT_DEPENDENCY_MISSING,
                                "message": f"{obj_type.value} '{canvas.name}' 依赖的命名空间 '{ns_key}' 未在YAML中声明",
                                "object_key": canvas.key,
                                "missing_dependency": ns_key,
                            }
                        )

        return errors

    @classmethod
    def identify_conflicts(cls, doc: YAMLDocument, current_team: int | None = None) -> list[dict]:
        """
        识别目标环境中的同名冲突

        Args:
            doc: YAML文档对象
            current_team: 当前组织ID，用于判断是否有权限访问冲突记录
        """
        conflicts = []
        all_actions = [ConflictAction.SKIP.value, ConflictAction.OVERWRITE.value, ConflictAction.RENAME.value]
        rename_only = [ConflictAction.RENAME.value]

        for ns in doc.namespaces:
            if NameSpace.objects.filter(name=ns.name).exists():
                conflicts.append(
                    {
                        "object_key": ns.key,
                        "object_type": ObjectType.NAMESPACE.value,
                        "reason": ConflictReason.NAME_CONFLICT,
                        "suggested_actions": all_actions,
                    }
                )

        for ds in doc.datasources:
            existing = DataSourceAPIModel.objects.filter(name=ds.name, rest_api=ds.rest_api).first()
            if existing:
                has_permission = cls._check_group_permission(existing, current_team)
                conflicts.append(
                    {
                        "object_key": ds.key,
                        "object_type": ObjectType.DATASOURCE.value,
                        "reason": ConflictReason.NAME_CONFLICT if has_permission else ConflictReason.NO_PERMISSION_CONFLICT,
                        "suggested_actions": all_actions if has_permission else rename_only,
                    }
                )

        canvas_checks = [
            (doc.dashboards, ObjectType.DASHBOARD, Dashboard),
            (doc.topologies, ObjectType.TOPOLOGY, Topology),
            (doc.architectures, ObjectType.ARCHITECTURE, Architecture),
            (doc.screens, ObjectType.SCREEN, Screen),
            (doc.reports, ObjectType.REPORT, Report),
            (doc.network_topologies, ObjectType.NETWORK_TOPOLOGY, NetworkTopology),
        ]

        for canvas_list, obj_type, model in canvas_checks:
            for canvas in canvas_list:
                existing = model.objects.filter(name=canvas.name).first()
                if existing:
                    has_permission = cls._check_group_permission(existing, current_team)
                    conflicts.append(
                        {
                            "object_key": canvas.key,
                            "object_type": obj_type.value,
                            "reason": ConflictReason.NAME_CONFLICT if has_permission else ConflictReason.NO_PERMISSION_CONFLICT,
                            "suggested_actions": all_actions if has_permission else rename_only,
                        }
                    )

        return conflicts

    @staticmethod
    def _check_group_permission(obj, current_team: int | None) -> bool:
        """检查当前组织是否有权限访问对象"""
        if current_team is None:
            return True
        groups = getattr(obj, "groups", None)
        if groups is None:
            return True
        return int(current_team) in groups

    @classmethod
    def has_canvas_objects(cls, doc: YAMLDocument) -> bool:
        """检查YAML是否包含画布对象"""
        return bool(doc.dashboards or doc.topologies or doc.architectures or doc.screens or doc.reports or doc.network_topologies)

    @classmethod
    def precheck(
        cls,
        yaml_content: str,
        target_directory_id: int | None = None,
        default_conflict_action: str = ConflictAction.RENAME.value,
        current_team: int | None = None,
    ) -> dict:
        """
        执行完整预检流程

        返回预检结果，包含：
        - valid: 是否通过预检
        - counts: 对象统计
        - conflicts: 冲突列表
        - warnings: 警告列表
        - errors: 错误列表
        """
        all_errors = []
        all_warnings = []
        conflicts = []

        # Step 1: 阈值检查
        all_errors.extend(cls.check_size_threshold(yaml_content))
        if all_errors:
            return cls._build_precheck_result(False, None, conflicts, all_warnings, all_errors)

        # Step 2: YAML解析
        data, parse_errors = cls.parse_yaml(yaml_content)
        all_errors.extend(parse_errors)
        if all_errors:
            return cls._build_precheck_result(False, None, conflicts, all_warnings, all_errors)

        # Step 3: schema校验
        doc, schema_errors = cls.validate_schema(data)
        all_errors.extend(schema_errors)
        if all_errors:
            return cls._build_precheck_result(False, None, conflicts, all_warnings, all_errors)

        # Step 4: 对象数量检查
        all_errors.extend(cls.check_object_counts_consistency(doc))
        all_errors.extend(cls.check_empty_import(doc))
        all_errors.extend(cls.check_object_limit(doc))
        if all_errors:
            return cls._build_precheck_result(False, doc, conflicts, all_warnings, all_errors)

        # Step 5: DB ID引用检查
        all_errors.extend(cls.check_db_id_references(data))

        # Step 6: 依赖完整性检查
        all_errors.extend(cls.check_dependencies(doc))

        # Step 7: 画布导入必须指定目录
        if cls.has_canvas_objects(doc) and target_directory_id is None:
            all_errors.append(
                {
                    "code": ImportExportErrorCode.IMPORT_TARGET_DIRECTORY_REQUIRED,
                    "message": "YAML包含画布对象，必须指定目标目录",
                }
            )

        # Step 8: 敏感字段警告
        all_warnings.extend(cls.check_sensitive_placeholders(doc))

        # Step 9: 冲突识别
        conflicts = cls.identify_conflicts(doc, current_team)

        valid = len(all_errors) == 0
        return cls._build_precheck_result(valid, doc, conflicts, all_warnings, all_errors)

    @staticmethod
    def _build_precheck_result(
        valid: bool,
        doc: YAMLDocument | None,
        conflicts: list,
        warnings: list,
        errors: list,
    ) -> dict:
        """构建预检结果结构"""
        counts = count_objects(doc) if doc else {"total": 0, "by_type": {}}

        return {
            "valid": valid,
            "counts": counts,
            "conflicts": conflicts,
            "warnings": warnings,
            "errors": errors,
            "_doc": doc,  # 供 submit 阶段直接使用，避免第二次 YAML 解析
        }
