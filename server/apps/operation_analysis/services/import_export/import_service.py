# -- coding: utf-8 --
"""
YAML导入执行服务

负责执行YAML导入操作，包括：
- 冲突决策处理（skip/overwrite/rename）
- 依赖顺序导入（namespace -> datasource -> canvas）
- 事务原子性保证
- 导入结果统计

Tech Plan参考：
- 2.1.5 /import/submit/ 接口
- 5.3 导入执行流程
"""

from copy import deepcopy

from django.db import transaction

from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.common.builtin_datasource_identity import find_claimable_datasource
from apps.operation_analysis.common.datasource_security import LEGACY_RAW_MONITOR_QUERY_ERROR, is_legacy_raw_monitor_query
from apps.operation_analysis.common.datasource_visibility import can_access_datasource_in_org
from apps.operation_analysis.constants.canvas_refresh import CANVAS_REFRESH_OBJECT_TYPES, normalize_canvas_refresh_interval
from apps.operation_analysis.constants.import_export import (
    RENAME_SUFFIX,
    SENSITIVE_PLACEHOLDER,
    ConflictAction,
    ImportExportErrorCode,
    ImportStatus,
    ObjectType,
    is_sensitive_field_name,
)
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, DataSourceTag, NameSpace
from apps.operation_analysis.models.models import Architecture, Dashboard, Directory, NetworkTopology, Report, Screen, Topology
from apps.operation_analysis.schemas.import_export_schema import (
    ArchitectureItem,
    DashboardItem,
    DatasourceItem,
    NamespaceItem,
    NetworkTopologyItem,
    ReportItem,
    ScreenItem,
    TopologyItem,
    YAMLDocument,
)
from apps.operation_analysis.services.import_export.datasource_package_identity import (
    HandleIndex,
    business_config_equal,
    find_identity_row,
    rewrite_datasource_bindings,
    unresolved_package_handles,
)
from apps.operation_analysis.services.import_export.view_sets import (
    rewrite_canvas_view_sets_refs_for_storage,
    rewrite_data_variables,
)
from apps.operation_analysis.services.string_param_multiple_migrate import migrate_filters_payload, migrate_param_items
from apps.operation_analysis.services.user_messages import oa_message

_LOG_TOKEN_LIMIT = 80


def _log_token(value: object, limit: int = _LOG_TOKEN_LIMIT) -> str:
    """日志只留短标签。去掉换行和控制符，避免上传名称把一条日志拆开。"""
    text = "".join(ch if ch.isprintable() and ch not in "\r\n\t" else " " for ch in str(value or ""))
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit]


class ImportService:
    """
    YAML导入执行服务

    遵循Tech Plan 5.3节导入流程：
    1. 依赖顺序导入：namespace -> datasource -> canvas
    2. 冲突处理：根据conflict_decisions执行skip/overwrite/rename
    3. 敏感字段补充：从secret_supplements中获取
    4. 原子事务：全成功或全回滚
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

    def __init__(
        self,
        doc: YAMLDocument,
        target_directory_id: int | None,
        conflict_decisions: dict[str, str],
        secret_supplements: dict[str, dict[str, str]],
        created_by: str = "",
        updated_by: str = "",
        groups: list[int] | None = None,
        existing_canvas_ids: dict[tuple[str, str], int] | None = None,
        preserve_existing_canvas_groups: bool = False,
        datasource_groups: list[int] | None = None,
        conflict_decisions_by_type: dict[tuple[str, str], str] | None = None,
        current_team: int | None = None,
        is_superuser: bool = False,
        builtin_seed: bool = False,
    ):
        """
        初始化导入服务

        Args:
            doc: 预检通过的YAMLDocument对象
            target_directory_id: 画布对象目标目录ID
            conflict_decisions: 冲突决策，key为object_key，value为skip/overwrite/rename
            secret_supplements: 敏感字段补充，key为object_key，value为{field: value}
            created_by: 创建者
            updated_by: 更新者
            groups: 导入画布所属的组织ID列表
            existing_canvas_ids: 由受信调用方按（对象类型，稳定键）解析的存量画布 ID
            preserve_existing_canvas_groups: 覆盖存量画布时保留其组织可见性配置
            datasource_groups: 新建数据源的组织名单；None 时沿用 groups
            conflict_decisions_by_type: 按（对象类型，object_key）分开的冲突决策。
                提供时优先于 conflict_decisions，避免画布键与数据源键相同互相覆盖。
        """
        self.doc = doc
        self.target_directory_id = target_directory_id
        self.conflict_decisions = conflict_decisions
        self.conflict_decisions_by_type = conflict_decisions_by_type
        self.secret_supplements = secret_supplements
        self.created_by = created_by
        self.updated_by = updated_by
        self.groups = groups or []
        self.datasource_groups = self.groups if datasource_groups is None else list(datasource_groups)
        self.existing_canvas_ids = existing_canvas_ids or {}
        self.preserve_existing_canvas_groups = preserve_existing_canvas_groups
        self.current_team = current_team
        self.is_superuser = is_superuser
        self.builtin_seed = builtin_seed
        self._handle_index = HandleIndex()

        # 导入过程中的映射表：YAML key -> DB ID
        self.namespace_key_to_id: dict[str, int] = {}
        self.datasource_key_to_id: dict[str, int] = {}
        self.tag_name_to_id: dict[str, int] = {}
        # 本次新建或内置种子更新的数据源。复用的目标行不在这里，避免改写它的参数。
        self.rewritable_datasource_keys: set[str] = set()
        self._pending_datasource_results: list[tuple[DatasourceItem, int, str, str]] = []

        # 导入结果统计
        self.results: list[dict] = []

    def _get_conflict_action(self, object_key: str, object_type: str | None = None) -> str:
        """获取对象的冲突处理策略，默认为rename。

        分类型决策存在时只查（对象类型，object_key），不再回落到扁平 object_key。
        """
        if self.conflict_decisions_by_type is not None and object_type is not None:
            return self.conflict_decisions_by_type.get((object_type, object_key), ConflictAction.RENAME.value)
        return self.conflict_decisions.get(object_key, ConflictAction.RENAME.value)

    def _get_secret_value(self, object_key: str, field: str, default: str = "") -> str:
        """获取敏感字段的补充值"""
        supplements = self.secret_supplements.get(object_key, {})
        return supplements.get(field, default)

    @staticmethod
    def _nested_value(value, path):
        current = value
        for item in path:
            if isinstance(item, str) and isinstance(current, dict):
                current = current.get(item)
            elif isinstance(item, int) and isinstance(current, list) and item < len(current):
                current = current[item]
            else:
                return None
        return current

    def _normalize_transform_config(self, ds_item) -> dict:
        config = getattr(ds_item, "transform_config", None)
        if not isinstance(config, dict):
            return {}
        enabled = bool(config.get("enabled"))
        script = config.get("script") if isinstance(config.get("script"), str) else ""
        if enabled and not script.strip():
            return {"enabled": False, "language": "python", "script": ""}
        return {
            "enabled": enabled,
            "language": "python",
            "script": script,
        }

    def _resolve_config_placeholders(self, object_key: str, field: str, config: dict, existing: dict | None = None):
        """用显式补密值或覆盖目标中的原值替换连接器配置里的脱敏占位符。"""
        resolved = deepcopy(config)
        missing = []
        supplements = self.secret_supplements.get(object_key, {})

        def visit(value, path, display_path):
            if isinstance(value, dict):
                for key, item in value.items():
                    item_path = (*path, key)
                    item_display_path = f"{display_path}.{key}"
                    if item == SENSITIVE_PLACEHOLDER and is_sensitive_field_name(key):
                        replacement = supplements.get(item_display_path, supplements.get(str(key)))
                        if replacement in (None, "", SENSITIVE_PLACEHOLDER) and existing is not None:
                            replacement = self._nested_value(existing, item_path)
                        if replacement in (None, "", SENSITIVE_PLACEHOLDER):
                            missing.append(item_display_path)
                        else:
                            value[key] = replacement
                    else:
                        visit(item, item_path, item_display_path)
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    visit(item, (*path, index), f"{display_path}[{index}]")

        visit(resolved, (), field)
        return resolved, missing

    def _prepare_datasource_configs(self, ds_item: DatasourceItem, existing: DataSourceAPIModel | None = None):
        connection_config, missing_connection = self._resolve_config_placeholders(
            ds_item.key,
            "connection_config",
            ds_item.connection_config,
            existing.connection_config if existing else None,
        )
        query_config, missing_query = self._resolve_config_placeholders(
            ds_item.key,
            "query_config",
            ds_item.query_config,
            existing.query_config if existing else None,
        )
        return connection_config, query_config, missing_connection + missing_query

    def _reset_excel_materialization_if_needs_upload(self, existing: DataSourceAPIModel, query_config: dict) -> None:
        """新格式 Excel（无 imported_items）覆盖时清空旧槽，强制 needs_upload。"""
        imported = query_config.get("imported_items") if isinstance(query_config, dict) else None
        if isinstance(imported, list) and imported:
            return
        if existing.source_type != DataSourceAPIModel.SOURCE_TYPE_EXCEL:
            return

        from apps.operation_analysis.services.excel_materialize import abandon_excel_materialization

        abandon_excel_materialization(existing, clear_excel_query_keys=False)

    def _generate_rename_name(self, original_name: str, model) -> str:
        """
        生成重命名后的名称

        规则：{original_name}_copy，若仍冲突则继续追加_copy
        """
        name_max_length = model._meta.get_field("name").max_length
        max_suffixes = (name_max_length - len(original_name)) // len(RENAME_SUFFIX)
        candidates = [f"{original_name}{RENAME_SUFFIX * count}" for count in range(1, max_suffixes + 1)]
        existing_names = set(model.objects.filter(name__in=candidates).values_list("name", flat=True))

        for candidate in candidates:
            if candidate not in existing_names:
                return candidate

        raise ValueError(oa_message("messages.import_rename_exhausted", "名称 {name} 已无可用的重命名空间", name=original_name))

    def _record_result(
        self,
        object_key: str,
        object_type: str,
        status: str,
        message: str = "",
        new_id: int | None = None,
        code: str | None = None,
    ):
        """记录单个对象的导入结果"""
        row = {
            "object_key": object_key,
            "object_type": object_type,
            "status": status,
            "message": message,
            "new_id": new_id,
        }
        if code:
            row["code"] = code
        self.results.append(row)

    def _has_failed_results(self) -> bool:
        return any(result["status"] == ImportStatus.FAILED.value for result in self.results)

    def _rollback_on_failure(self) -> dict | None:
        if not self._has_failed_results():
            return None

        transaction.set_rollback(True)
        summary = self._build_summary()
        logger.warning("[CanvasImport] 存在导入失败项，事务已回滚：%s", summary)
        return {
            "success": False,
            "results": self.results,
            "summary": summary,
        }

    def _import_namespace(self, ns_item: NamespaceItem) -> int | None:
        """
        导入单个命名空间

        Returns:
            新建或已存在的命名空间ID
        """
        existing = NameSpace.objects.filter(name=ns_item.name).first()
        action = self._get_conflict_action(ns_item.key, ObjectType.NAMESPACE.value)

        # 获取密码值（优先使用supplement，否则使用YAML中的值）
        password = self._get_secret_value(ns_item.key, "password")
        if not password or password == SENSITIVE_PLACEHOLDER:
            password = ns_item.password if ns_item.password != SENSITIVE_PLACEHOLDER else ""

        if existing:
            if action == ConflictAction.SKIP.value:
                self._record_result(
                    ns_item.key,
                    ObjectType.NAMESPACE.value,
                    ImportStatus.SKIPPED.value,
                    oa_message("messages.import_namespace_skipped", "跳过已存在的命名空间"),
                    existing.id,
                )
                return existing.id

            elif action == ConflictAction.OVERWRITE.value:
                # 全量覆盖
                existing.domain = ns_item.domain
                existing.namespace = ns_item.namespace
                existing.account = ns_item.account
                if password and password != SENSITIVE_PLACEHOLDER:
                    existing.set_password(password)
                existing.enable_tls = ns_item.enable_tls
                existing.desc = ns_item.desc
                existing.updated_by = self.updated_by
                existing.save()
                self._record_result(
                    ns_item.key,
                    ObjectType.NAMESPACE.value,
                    ImportStatus.OVERWRITTEN.value,
                    oa_message("messages.import_namespace_overwritten", "覆盖已存在的命名空间"),
                    existing.id,
                )
                return existing.id

            else:  # rename
                new_name = self._generate_rename_name(ns_item.name, NameSpace)
                ns = NameSpace(
                    name=new_name,
                    domain=ns_item.domain,
                    namespace=ns_item.namespace,
                    account=ns_item.account,
                    enable_tls=ns_item.enable_tls,
                    desc=ns_item.desc,
                    created_by=self.created_by,
                    updated_by=self.updated_by,
                )
                if password and password != SENSITIVE_PLACEHOLDER:
                    ns.set_password(password)
                ns.save()
                self._record_result(
                    ns_item.key,
                    ObjectType.NAMESPACE.value,
                    ImportStatus.SUCCESS.value,
                    oa_message("messages.import_renamed", "重命名为 {name}", name=new_name),
                    ns.id,
                )
                return ns.id
        else:
            # 新建
            if not password or password == SENSITIVE_PLACEHOLDER:
                self._record_result(
                    ns_item.key,
                    ObjectType.NAMESPACE.value,
                    ImportStatus.FAILED.value,
                    oa_message("messages.import_namespace_password_missing", "新建命名空间缺少密码"),
                    code=ImportExportErrorCode.IMPORT_SECRET_REQUIRED,
                )
                return None

            ns = NameSpace(
                name=ns_item.name,
                domain=ns_item.domain,
                namespace=ns_item.namespace,
                account=ns_item.account,
                enable_tls=ns_item.enable_tls,
                desc=ns_item.desc,
                created_by=self.created_by,
                updated_by=self.updated_by,
            )
            ns.set_password(password)
            ns.save()
            self._record_result(
                ns_item.key,
                ObjectType.NAMESPACE.value,
                ImportStatus.SUCCESS.value,
                oa_message("messages.import_namespace_created", "新建命名空间"),
                ns.id,
            )
            return ns.id

    def _package_datasource_keys(self) -> set[str]:
        keys: set[str] = set()
        for item in self.doc.datasources:
            keys.add(item.key)
            identity = item.identity
            if identity is None:
                continue
            if identity.kind == "builtin" and identity.build_in_key:
                keys.add(identity.build_in_key)
                keys.add(f"builtin::{identity.build_in_key}")
            if identity.kind == "portable" and identity.portable_key:
                keys.add(f"portable::{identity.portable_key}")
        return keys

    def _bind_datasource_key(self, ds_item: DatasourceItem, datasource_id: int) -> None:
        self.datasource_key_to_id[ds_item.key] = datasource_id
        identity = ds_item.identity
        if identity is None:
            return
        if identity.kind == "builtin" and identity.build_in_key:
            self.datasource_key_to_id[f"builtin::{identity.build_in_key}"] = datasource_id
            self.datasource_key_to_id[identity.build_in_key] = datasource_id
        if identity.kind == "portable" and identity.portable_key:
            self.datasource_key_to_id[f"portable::{identity.portable_key}"] = datasource_id

    def _fail_datasource(self, ds_item: DatasourceItem, message: str, code: str) -> None:
        self._record_result(
            ds_item.key,
            ObjectType.DATASOURCE.value,
            ImportStatus.FAILED.value,
            message,
            code=code,
        )

    def _namespace_nats(self) -> dict[str, str]:
        return {item.name: item.namespace or "" for item in self.doc.namespaces}

    def _can_access_datasource(self, row: DataSourceAPIModel) -> bool:
        # 与解析、预检同一套组织判断。超级用户当前组织看不到的行，不能当成有权复用。
        if self.current_team is None:
            return True
        return can_access_datasource_in_org(row, self.current_team)

    def _relation_ids(self, ds_item: DatasourceItem) -> tuple[list[int], list[int]]:
        namespace_ids = [self.namespace_key_to_id[ns_key] for ns_key in ds_item.namespace_keys if ns_key in self.namespace_key_to_id]
        tag_ids = [self.tag_name_to_id[tag_name] for tag_name in ds_item.tags if tag_name in self.tag_name_to_id]
        return namespace_ids, tag_ids

    def _remember_new_datasource(self, ds_item: DatasourceItem, datasource_id: int, status: str, message: str) -> None:
        self.rewritable_datasource_keys.add(ds_item.key)
        self._bind_datasource_key(ds_item, datasource_id)
        self._pending_datasource_results.append((ds_item, datasource_id, status, message))

    def _create_user_datasource(self, ds_item: DatasourceItem, *, adopt_identity: bool) -> int | None:
        """新建数据源。首次到达时继承包内身份；冲突副本去掉原身份并另发一把。"""
        connection_config, query_config, missing_secrets = self._prepare_datasource_configs(ds_item)
        if missing_secrets:
            self._fail_datasource(
                ds_item,
                oa_message(
                    "messages.import_datasource_secrets_missing",
                    "数据源缺少敏感配置: {fields}",
                    fields=", ".join(missing_secrets),
                ),
                ImportExportErrorCode.IMPORT_SECRET_REQUIRED,
            )
            return None
        name = ds_item.name
        renamed = ""
        if DataSourceAPIModel.objects.filter(name=name, rest_api=ds_item.rest_api).exists():
            name = self._generate_rename_name(name, DataSourceAPIModel)
            renamed = name
        is_build_in = False
        build_in_key = None
        portable_key = None
        identity = ds_item.identity
        if adopt_identity and identity is not None:
            if identity.kind == "builtin" and identity.build_in_key:
                is_build_in = True
                build_in_key = identity.build_in_key
            elif identity.kind == "portable" and identity.portable_key:
                portable_key = identity.portable_key
        datasource = DataSourceAPIModel.objects.create(
            name=name,
            rest_api=ds_item.rest_api,
            source_type=ds_item.source_type,
            connection=None,
            connection_overrides={},
            connection_config=connection_config,
            query_config=query_config,
            transform_config=self._normalize_transform_config(ds_item),
            desc=ds_item.desc,
            is_active=ds_item.is_active,
            params=migrate_param_items(ds_item.params)[0],
            chart_type=ds_item.chart_type,
            field_schema=ds_item.field_schema,
            created_by=self.created_by,
            updated_by=self.updated_by,
            groups=self.datasource_groups,
            is_build_in=is_build_in,
            build_in_key=build_in_key,
            portable_key=portable_key,
        )
        namespace_ids, tag_ids = self._relation_ids(ds_item)
        datasource.namespaces.set(namespace_ids)
        datasource.tag.set(tag_ids)
        message = (
            oa_message("messages.import_renamed", "重命名为 {name}", name=renamed)
            if renamed
            else oa_message("messages.import_datasource_created", "新建数据源")
        )
        self._remember_new_datasource(ds_item, datasource.id, ImportStatus.SUCCESS.value, message)
        return datasource.id

    def _reuse_datasource(self, ds_item: DatasourceItem, existing: DataSourceAPIModel) -> int:
        """沿用目标行。不改它的参数，也不改已经指向它的画布。"""
        self._bind_datasource_key(ds_item, existing.id)
        self._record_result(
            ds_item.key,
            ObjectType.DATASOURCE.value,
            ImportStatus.SKIPPED.value,
            oa_message("messages.import_datasource_reused", "复用目标配置"),
            existing.id,
        )
        return existing.id

    def _apply_datasource_fields(self, existing: DataSourceAPIModel, ds_item: DatasourceItem) -> list[str] | None:
        connection_config, query_config, missing_secrets = self._prepare_datasource_configs(ds_item, existing)
        if missing_secrets:
            return missing_secrets
        previous_source_type = existing.source_type
        existing.desc = ds_item.desc
        existing.source_type = ds_item.source_type
        existing.connection = None
        existing.connection_overrides = {}
        existing.connection_config = connection_config
        existing.query_config = query_config
        existing.transform_config = self._normalize_transform_config(ds_item)
        existing.is_active = ds_item.is_active
        existing.params = migrate_param_items(ds_item.params)[0]
        existing.chart_type = ds_item.chart_type
        existing.field_schema = ds_item.field_schema
        existing.updated_by = self.updated_by
        existing.save()
        if previous_source_type == DataSourceAPIModel.SOURCE_TYPE_EXCEL and existing.source_type != DataSourceAPIModel.SOURCE_TYPE_EXCEL:
            from apps.operation_analysis.services.excel_materialize import abandon_excel_materialization

            abandon_excel_materialization(existing, clear_excel_query_keys=False)
        elif existing.source_type == DataSourceAPIModel.SOURCE_TYPE_EXCEL:
            self._reset_excel_materialization_if_needs_upload(existing, query_config)
        namespace_ids, tag_ids = self._relation_ids(ds_item)
        existing.namespaces.set(namespace_ids)
        existing.tag.set(tag_ids)
        return None

    def _import_builtin_seed_datasource(self, ds_item: DatasourceItem) -> int | None:
        """内置种子可以原地更新认领到的行。用户导入不会走到这里。"""
        identity = ds_item.identity
        stable_key = identity.build_in_key if identity is not None and identity.kind == "builtin" and identity.build_in_key else ds_item.key
        try:
            existing = find_claimable_datasource(
                DataSourceAPIModel,
                stable_key=stable_key,
                name=ds_item.name,
                rest_api=ds_item.rest_api,
            )
        except ValueError:
            self._fail_datasource(
                ds_item,
                oa_message("messages.import_builtin_identity_conflict", "内置数据源稳定身份冲突"),
                ImportExportErrorCode.IMPORT_CONFLICT_UNRESOLVED,
            )
            return None
        if existing is None:
            connection_config, query_config, missing_secrets = self._prepare_datasource_configs(ds_item)
            if missing_secrets:
                self._fail_datasource(
                    ds_item,
                    oa_message(
                        "messages.import_datasource_secrets_missing",
                        "数据源缺少敏感配置: {fields}",
                        fields=", ".join(missing_secrets),
                    ),
                    ImportExportErrorCode.IMPORT_SECRET_REQUIRED,
                )
                return None
            datasource = DataSourceAPIModel(
                name=ds_item.name,
                rest_api=ds_item.rest_api,
                source_type=ds_item.source_type,
                connection=None,
                connection_overrides={},
                connection_config=connection_config,
                query_config=query_config,
                transform_config=self._normalize_transform_config(ds_item),
                desc=ds_item.desc,
                is_active=ds_item.is_active,
                params=migrate_param_items(ds_item.params)[0],
                chart_type=ds_item.chart_type,
                field_schema=ds_item.field_schema,
                created_by=self.created_by,
                updated_by=self.updated_by,
                groups=self.datasource_groups,
                is_build_in=True,
                build_in_key=stable_key,
                portable_key=None,
            )
            datasource.save()
            namespace_ids, tag_ids = self._relation_ids(ds_item)
            datasource.namespaces.set(namespace_ids)
            datasource.tag.set(tag_ids)
            self._remember_new_datasource(
                ds_item,
                datasource.id,
                ImportStatus.SUCCESS.value,
                oa_message("messages.import_datasource_created", "新建数据源"),
            )
            return datasource.id

        if existing.portable_key and not existing.is_build_in and not existing.build_in_key:
            self._fail_datasource(
                ds_item,
                oa_message(
                    "messages.import_builtin_user_identity_protected",
                    "该行已有用户身份，不能认领为内置源",
                ),
                ImportExportErrorCode.IMPORT_CONFLICT_UNRESOLVED,
            )
            return None
        existing.is_build_in = True
        existing.build_in_key = stable_key
        missing_secrets = self._apply_datasource_fields(existing, ds_item)
        if missing_secrets:
            self._fail_datasource(
                ds_item,
                oa_message(
                    "messages.import_datasource_secrets_missing",
                    "数据源缺少敏感配置: {fields}",
                    fields=", ".join(missing_secrets),
                ),
                ImportExportErrorCode.IMPORT_SECRET_REQUIRED,
            )
            return None
        existing.save()
        self._remember_new_datasource(
            ds_item,
            existing.id,
            ImportStatus.OVERWRITTEN.value,
            oa_message("messages.import_datasource_overwritten", "覆盖已存在的数据源"),
        )
        return existing.id

    def _rewrite_fresh_datasource_params(self) -> None:
        """全部源落库后再改写新建行的引用。复用行不进这个列表。"""
        package_keys = self._package_datasource_keys()
        for ds_item, datasource_id, status, message in self._pending_datasource_results:
            row = DataSourceAPIModel.objects.filter(pk=datasource_id).first()
            if row is None:
                self._fail_datasource(
                    ds_item,
                    oa_message("messages.import_dependency_missing", "缺少依赖的数据源，已停止导入"),
                    ImportExportErrorCode.IMPORT_DEPENDENCY_MISSING,
                )
                continue
            missing = unresolved_package_handles(row.params, self.datasource_key_to_id, package_keys)
            if missing:
                self._fail_datasource(
                    ds_item,
                    oa_message("messages.import_dependency_missing", "缺少依赖的数据源，已停止导入"),
                    ImportExportErrorCode.IMPORT_DEPENDENCY_MISSING,
                )
                continue
            rewritten = rewrite_datasource_bindings(row.params, self.datasource_key_to_id)
            if rewritten != row.params:
                row.params = rewritten
                row.save(update_fields=["params", "updated_at"])
            self._record_result(ds_item.key, ObjectType.DATASOURCE.value, status, message, datasource_id)

    def _import_datasource(self, ds_item: DatasourceItem) -> int | None:
        """
        导入单个数据源。

        有稳定身份时按身份对齐。配置相同就复用，不改目标行。
        配置不同时，只有复用或跳过会指向原行；作为新数据源导入会另建一行。
        没有稳定身份的旧包不会按名称并到已有行。
        """
        action = self._get_conflict_action(ds_item.key, ObjectType.DATASOURCE.value)

        targets_legacy_route = is_legacy_raw_monitor_query(
            source_type=ds_item.source_type,
            rest_api=ds_item.rest_api,
        )
        if targets_legacy_route:
            self._record_result(
                ds_item.key,
                ObjectType.DATASOURCE.value,
                ImportStatus.FAILED.value,
                oa_message("messages.import_legacy_raw_monitor", LEGACY_RAW_MONITOR_QUERY_ERROR),
                code=ImportExportErrorCode.YAML_SCHEMA_INVALID,
            )
            return None

        if self.builtin_seed:
            return self._import_builtin_seed_datasource(ds_item)

        existing = find_identity_row(ds_item, lock=True)
        if existing is not None:
            if not self._can_access_datasource(existing):
                if action in {ConflictAction.IMPORT_AS_NEW.value, ConflictAction.RENAME.value}:
                    return self._create_user_datasource(ds_item, adopt_identity=False)
                self._fail_datasource(
                    ds_item,
                    oa_message("messages.import_datasource_forbidden", "无权使用目标环境中的同身份数据源"),
                    ImportExportErrorCode.IMPORT_PERMISSION_DENIED,
                )
                return None
            same_config = business_config_equal(
                ds_item,
                existing,
                handle_index=self._handle_index.cover(ds_item, existing),
                namespace_nats=self._namespace_nats(),
            )
            if same_config or action in {ConflictAction.REUSE_TARGET.value, ConflictAction.SKIP.value}:
                if action == ConflictAction.OVERWRITE.value and not same_config:
                    self._fail_datasource(
                        ds_item,
                        oa_message("messages.import_identity_overwrite_forbidden", "同一身份的数据源不能直接覆盖，请选择复用或作为新数据源导入"),
                        ImportExportErrorCode.IMPORT_CONFLICT_UNRESOLVED,
                    )
                    return None
                return self._reuse_datasource(ds_item, existing)
            if action in {ConflictAction.IMPORT_AS_NEW.value, ConflictAction.RENAME.value}:
                return self._create_user_datasource(ds_item, adopt_identity=False)
            self._fail_datasource(
                ds_item,
                oa_message("messages.import_identity_overwrite_forbidden", "同一身份的数据源不能直接覆盖，请选择复用或作为新数据源导入"),
                ImportExportErrorCode.IMPORT_CONFLICT_UNRESOLVED,
            )
            return None

        name_taken = DataSourceAPIModel.objects.filter(name=ds_item.name, rest_api=ds_item.rest_api).exists()
        if name_taken and action == ConflictAction.SKIP.value:
            self._record_result(
                ds_item.key,
                ObjectType.DATASOURCE.value,
                ImportStatus.SKIPPED.value,
                oa_message("messages.import_datasource_skipped", "跳过已存在的数据源"),
            )
            return None
        if name_taken and action in {ConflictAction.OVERWRITE.value, ConflictAction.REUSE_TARGET.value}:
            self._fail_datasource(
                ds_item,
                oa_message("messages.import_legacy_name_attach_forbidden", "旧包没有稳定身份，不能按名称覆盖或复用已有数据源"),
                ImportExportErrorCode.IMPORT_CONFLICT_UNRESOLVED,
            )
            return None
        return self._create_user_datasource(ds_item, adopt_identity=True)

    def _import_canvas(
        self,
        canvas_item: DashboardItem | TopologyItem | ArchitectureItem | ScreenItem | ReportItem | NetworkTopologyItem,
        object_type: ObjectType,
        model,
    ) -> int | None:
        """
        导入单个画布对象

        Returns:
            新建或已存在的画布ID
        """
        stable_existing_id = self.existing_canvas_ids.get((object_type.value, canvas_item.key))
        if stable_existing_id is not None:
            existing = model.objects.filter(pk=stable_existing_id).first()
        else:
            existing = model.objects.filter(name=canvas_item.name).first()
        action = self._get_conflict_action(canvas_item.key, object_type.value)
        if not (existing and action == ConflictAction.SKIP.value):
            package_keys = self._package_datasource_keys()
            missing = unresolved_package_handles(canvas_item.view_sets, self.datasource_key_to_id, package_keys)
            if object_type == ObjectType.DASHBOARD and hasattr(canvas_item, "filters"):
                missing.extend(unresolved_package_handles(canvas_item.filters, self.datasource_key_to_id, package_keys))
            if missing:
                self._record_result(
                    canvas_item.key,
                    object_type.value,
                    ImportStatus.FAILED.value,
                    oa_message("messages.import_dependency_missing", "缺少依赖的数据源，已停止导入"),
                    code=ImportExportErrorCode.IMPORT_DEPENDENCY_MISSING,
                )
                return None

        # 获取目标目录
        directory = None
        if self.target_directory_id:
            directory = Directory.objects.filter(id=self.target_directory_id).first()

        canvas_groups = directory.groups if directory is not None else self.groups

        # 构建基础数据
        canvas_data = {
            "desc": canvas_item.desc,
            "view_sets": rewrite_canvas_view_sets_refs_for_storage(
                canvas_item.view_sets,
                object_type,
                self.datasource_key_to_id,
            ),
            "directory": directory,
        }
        if existing is None or not (stable_existing_id is not None and self.preserve_existing_canvas_groups):
            canvas_data["groups"] = canvas_groups

        if stable_existing_id is not None:
            name_conflict = model.objects.filter(name=canvas_item.name).exclude(pk=stable_existing_id).exists()
            if name_conflict:
                logger.warning(
                    "[CanvasImport] builtin canvas name is taken; object_type=%s key=%s name=%s",
                    object_type.value,
                    _log_token(canvas_item.key),
                    _log_token(canvas_item.name),
                )
            else:
                canvas_data["name"] = canvas_item.name

        if object_type == ObjectType.NETWORK_TOPOLOGY:
            canvas_data["base_url"] = canvas_item.base_url
            token = self._get_secret_value(canvas_item.key, "token")
            if not token and canvas_item.token != SENSITIVE_PLACEHOLDER:
                token = canvas_item.token
            if token and token != SENSITIVE_PLACEHOLDER:
                canvas_data["token"] = token
        else:
            other = canvas_item.other
            if isinstance(other, dict) and isinstance(other.get("dataVariables"), list):
                other = dict(other)
                other["dataVariables"] = rewrite_data_variables(
                    other.get("dataVariables"),
                    self.datasource_key_to_id,
                )
            canvas_data["other"] = other

        # Dashboard有额外的filters字段
        if object_type == ObjectType.DASHBOARD and hasattr(canvas_item, "filters"):
            canvas_data["filters"] = rewrite_datasource_bindings(
                migrate_filters_payload(canvas_item.filters)[0],
                self.datasource_key_to_id,
            )

        if object_type in CANVAS_REFRESH_OBJECT_TYPES:
            canvas_data["refresh_interval"] = normalize_canvas_refresh_interval(getattr(canvas_item, "refresh_interval", 0))

        if existing:
            if action == ConflictAction.SKIP.value:
                self._record_result(
                    canvas_item.key,
                    object_type.value,
                    ImportStatus.SKIPPED.value,
                    oa_message("messages.import_canvas_skipped", "跳过已存在的{object_type}", object_type=object_type.value),
                    existing.id,
                )
                return existing.id

            elif action == ConflictAction.OVERWRITE.value:
                for key, value in canvas_data.items():
                    setattr(existing, key, value)
                existing.updated_by = self.updated_by
                existing.save()
                self._record_result(
                    canvas_item.key,
                    object_type.value,
                    ImportStatus.OVERWRITTEN.value,
                    oa_message("messages.import_canvas_overwritten", "覆盖已存在的{object_type}", object_type=object_type.value),
                    existing.id,
                )
                return existing.id

            else:  # rename
                new_name = self._generate_rename_name(canvas_item.name, model)
                canvas_data["name"] = new_name
                canvas_data["created_by"] = self.created_by
                canvas_data["updated_by"] = self.updated_by
                canvas = model.objects.create(**canvas_data)
                self._record_result(
                    canvas_item.key,
                    object_type.value,
                    ImportStatus.SUCCESS.value,
                    oa_message("messages.import_renamed", "重命名为 {name}", name=new_name),
                    canvas.id,
                )
                return canvas.id
        else:
            # 新建
            canvas_data["name"] = canvas_item.name
            canvas_data["created_by"] = self.created_by
            canvas_data["updated_by"] = self.updated_by
            canvas = model.objects.create(**canvas_data)
            self._record_result(
                canvas_item.key,
                object_type.value,
                ImportStatus.SUCCESS.value,
                oa_message("messages.import_canvas_created", "新建{object_type}", object_type=object_type.value),
                canvas.id,
            )
            return canvas.id

    @transaction.atomic
    def execute(self) -> dict:
        """
        执行导入

        按依赖顺序导入：namespace -> datasource -> canvas
        整个过程在事务中执行，任一失败则回滚。

        Returns:
            {
                "success": bool,
                "results": [...],
                "summary": {
                    "total": int,
                    "success": int,
                    "failed": int,
                    "skipped": int,
                    "overwritten": int
                }
            }
        """
        logger.info(
            "[CanvasImport] 开始导入：命名空间 %s、数据源 %s、仪表盘 %s、拓扑 %s、架构 %s、大屏 %s、报表 %s、网络拓扑 %s",
            len(self.doc.namespaces),
            len(self.doc.datasources),
            len(self.doc.dashboards),
            len(self.doc.topologies),
            len(self.doc.architectures),
            len(self.doc.screens),
            len(self.doc.reports),
            len(self.doc.network_topologies),
        )

        try:
            # Step 1: 导入命名空间
            for ns_item in self.doc.namespaces:
                ns_id = self._import_namespace(ns_item)
                if ns_id:
                    self.namespace_key_to_id[ns_item.key] = ns_id

            rollback_result = self._rollback_on_failure()
            if rollback_result:
                return rollback_result

            # Step 2: 导入数据源
            namespace_keys = {
                ns_key for ds_item in self.doc.datasources for ns_key in ds_item.namespace_keys if ns_key not in self.namespace_key_to_id
            }
            self.namespace_key_to_id.update(NameSpace.objects.filter(name__in=namespace_keys).values_list("name", "id"))
            tag_names = {tag_name for ds_item in self.doc.datasources for tag_name in ds_item.tags}
            self.tag_name_to_id.update(DataSourceTag.objects.filter(name__in=tag_names).values_list("name", "id"))
            for ds_item in self.doc.datasources:
                ds_id = self._import_datasource(ds_item)
                if ds_id:
                    self.datasource_key_to_id[ds_item.key] = ds_id

            self._rewrite_fresh_datasource_params()

            rollback_result = self._rollback_on_failure()
            if rollback_result:
                return rollback_result

            # Step 3: 导入画布对象
            for dashboard in self.doc.dashboards:
                self._import_canvas(dashboard, ObjectType.DASHBOARD, Dashboard)

            for topology in self.doc.topologies:
                self._import_canvas(topology, ObjectType.TOPOLOGY, Topology)

            for architecture in self.doc.architectures:
                self._import_canvas(architecture, ObjectType.ARCHITECTURE, Architecture)

            for screen in self.doc.screens:
                self._import_canvas(screen, ObjectType.SCREEN, Screen)

            for report in self.doc.reports:
                self._import_canvas(report, ObjectType.REPORT, Report)

            for network_topology in self.doc.network_topologies:
                self._import_canvas(network_topology, ObjectType.NETWORK_TOPOLOGY, NetworkTopology)

            rollback_result = self._rollback_on_failure()
            if rollback_result:
                return rollback_result

            # 统计结果
            summary = self._build_summary()

            logger.info("[CanvasImport] 导入完成：%s", summary)

            return {
                "success": summary["failed"] == 0,
                "results": self.results,
                "summary": summary,
            }

        except Exception as e:
            logger.error("[CanvasImport] 导入过程异常中断：%s", e, exc_info=True)
            raise

    def _build_summary(self) -> dict:
        """构建导入结果统计"""
        summary = {
            "total": len(self.results),
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "overwritten": 0,
        }

        for result in self.results:
            status = result["status"]
            if status == ImportStatus.SUCCESS.value:
                summary["success"] += 1
            elif status == ImportStatus.FAILED.value:
                summary["failed"] += 1
            elif status == ImportStatus.SKIPPED.value:
                summary["skipped"] += 1
            elif status == ImportStatus.OVERWRITTEN.value:
                summary["overwritten"] += 1

        return summary
