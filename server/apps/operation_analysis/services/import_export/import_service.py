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
from apps.operation_analysis.constants.import_export import (
    RENAME_SUFFIX,
    SENSITIVE_PLACEHOLDER,
    ConflictAction,
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
from apps.operation_analysis.services.import_export.view_sets import normalize_canvas_view_sets_for_storage, rewrite_canvas_view_sets_refs_for_storage


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
            groups: 导入对象所属的组织ID列表
        """
        self.doc = doc
        self.target_directory_id = target_directory_id
        self.conflict_decisions = conflict_decisions
        self.secret_supplements = secret_supplements
        self.created_by = created_by
        self.updated_by = updated_by
        self.groups = groups or []

        # 导入过程中的映射表：YAML key -> DB ID
        self.namespace_key_to_id: dict[str, int] = {}
        self.datasource_key_to_id: dict[str, int] = {}
        self.tag_name_to_id: dict[str, int] = {}

        # 导入结果统计
        self.results: list[dict] = []

    def _get_conflict_action(self, object_key: str) -> str:
        """获取对象的冲突处理策略，默认为rename"""
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

    def _generate_rename_name(self, original_name: str, model) -> str:
        """
        生成重命名后的名称

        规则：{original_name}_copy，若仍冲突则继续追加_copy
        """
        new_name = f"{original_name}{RENAME_SUFFIX}"
        while model.objects.filter(name=new_name).exists():
            new_name = f"{new_name}{RENAME_SUFFIX}"
        return new_name

    def _record_result(
        self,
        object_key: str,
        object_type: str,
        status: str,
        message: str = "",
        new_id: int | None = None,
    ):
        """记录单个对象的导入结果"""
        self.results.append(
            {
                "object_key": object_key,
                "object_type": object_type,
                "status": status,
                "message": message,
                "new_id": new_id,
            }
        )

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
        action = self._get_conflict_action(ns_item.key)

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
                    "跳过已存在的命名空间",
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
                    "覆盖已存在的命名空间",
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
                    f"重命名为 {new_name}",
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
                    "新建命名空间缺少密码",
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
                "新建命名空间",
                ns.id,
            )
            return ns.id

    def _import_datasource(self, ds_item: DatasourceItem) -> int | None:
        """
        导入单个数据源

        Returns:
            新建或已存在的数据源ID
        """
        existing = DataSourceAPIModel.objects.filter(name=ds_item.name, rest_api=ds_item.rest_api).first()
        action = self._get_conflict_action(ds_item.key)

        # 解析关联的命名空间ID
        namespace_ids = [
            self.namespace_key_to_id[ns_key]
            for ns_key in ds_item.namespace_keys
            if ns_key in self.namespace_key_to_id
        ]

        # 解析tags
        tag_ids = [self.tag_name_to_id[tag_name] for tag_name in ds_item.tags if tag_name in self.tag_name_to_id]

        if existing:
            if action == ConflictAction.SKIP.value:
                self._record_result(
                    ds_item.key,
                    ObjectType.DATASOURCE.value,
                    ImportStatus.SKIPPED.value,
                    "跳过已存在的数据源",
                    existing.id,
                )
                return existing.id

            elif action == ConflictAction.OVERWRITE.value:
                connection_config, query_config, missing_secrets = self._prepare_datasource_configs(ds_item, existing)
                if missing_secrets:
                    self._record_result(
                        ds_item.key,
                        ObjectType.DATASOURCE.value,
                        ImportStatus.FAILED.value,
                        f"数据源缺少敏感配置: {', '.join(missing_secrets)}",
                    )
                    return None
                existing.desc = ds_item.desc
                existing.source_type = ds_item.source_type
                existing.connection_config = connection_config
                existing.query_config = query_config
                # [内部预留] is_active 字段仅内部使用，无产品功能依赖
                existing.is_active = ds_item.is_active
                existing.params = ds_item.params
                existing.chart_type = ds_item.chart_type
                existing.field_schema = ds_item.field_schema
                existing.updated_by = self.updated_by
                existing.save()
                existing.namespaces.set(namespace_ids)
                existing.tag.set(tag_ids)
                self._record_result(
                    ds_item.key,
                    ObjectType.DATASOURCE.value,
                    ImportStatus.OVERWRITTEN.value,
                    "覆盖已存在的数据源",
                    existing.id,
                )
                return existing.id

            else:  # rename
                connection_config, query_config, missing_secrets = self._prepare_datasource_configs(ds_item)
                if missing_secrets:
                    self._record_result(
                        ds_item.key,
                        ObjectType.DATASOURCE.value,
                        ImportStatus.FAILED.value,
                        f"数据源缺少敏感配置: {', '.join(missing_secrets)}",
                    )
                    return None
                new_name = self._generate_rename_name(ds_item.name, DataSourceAPIModel)
                ds = DataSourceAPIModel.objects.create(
                    name=new_name,
                    rest_api=ds_item.rest_api,
                    source_type=ds_item.source_type,
                    connection_config=connection_config,
                    query_config=query_config,
                    desc=ds_item.desc,
                    # [内部预留] is_active 字段仅内部使用，无产品功能依赖
                    is_active=ds_item.is_active,
                    params=ds_item.params,
                    chart_type=ds_item.chart_type,
                    field_schema=ds_item.field_schema,
                    created_by=self.created_by,
                    updated_by=self.updated_by,
                    groups=self.groups,
                )
                ds.namespaces.set(namespace_ids)
                ds.tag.set(tag_ids)
                self._record_result(
                    ds_item.key,
                    ObjectType.DATASOURCE.value,
                    ImportStatus.SUCCESS.value,
                    f"重命名为 {new_name}",
                    ds.id,
                )
                return ds.id
        else:
            # 新建
            connection_config, query_config, missing_secrets = self._prepare_datasource_configs(ds_item)
            if missing_secrets:
                self._record_result(
                    ds_item.key,
                    ObjectType.DATASOURCE.value,
                    ImportStatus.FAILED.value,
                    f"数据源缺少敏感配置: {', '.join(missing_secrets)}",
                )
                return None
            ds = DataSourceAPIModel.objects.create(
                name=ds_item.name,
                rest_api=ds_item.rest_api,
                source_type=ds_item.source_type,
                connection_config=connection_config,
                query_config=query_config,
                desc=ds_item.desc,
                # [内部预留] is_active 字段仅内部使用，无产品功能依赖
                is_active=ds_item.is_active,
                params=ds_item.params,
                chart_type=ds_item.chart_type,
                field_schema=ds_item.field_schema,
                created_by=self.created_by,
                updated_by=self.updated_by,
                groups=self.groups,
            )
            ds.namespaces.set(namespace_ids)
            ds.tag.set(tag_ids)
            self._record_result(
                ds_item.key,
                ObjectType.DATASOURCE.value,
                ImportStatus.SUCCESS.value,
                "新建数据源",
                ds.id,
            )
            return ds.id

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
        existing = model.objects.filter(name=canvas_item.name).first()
        action = self._get_conflict_action(canvas_item.key)

        # 获取目标目录
        directory = None
        if self.target_directory_id:
            directory = Directory.objects.filter(id=self.target_directory_id).first()

        canvas_groups = directory.groups if directory is not None else self.groups

        # 构建基础数据
        canvas_data = {
            "desc": canvas_item.desc,
            "view_sets": rewrite_canvas_view_sets_refs_for_storage(
                normalize_canvas_view_sets_for_storage(canvas_item.view_sets, object_type),
                object_type,
                self.datasource_key_to_id,
            ),
            "directory": directory,
            "groups": canvas_groups,
        }

        if object_type == ObjectType.NETWORK_TOPOLOGY:
            canvas_data["base_url"] = canvas_item.base_url
            token = self._get_secret_value(canvas_item.key, "token")
            if not token and canvas_item.token != SENSITIVE_PLACEHOLDER:
                token = canvas_item.token
            if token and token != SENSITIVE_PLACEHOLDER:
                canvas_data["token"] = token
        else:
            canvas_data["other"] = canvas_item.other

        # Dashboard有额外的filters字段
        if object_type == ObjectType.DASHBOARD and hasattr(canvas_item, "filters"):
            canvas_data["filters"] = canvas_item.filters

        if existing:
            if action == ConflictAction.SKIP.value:
                self._record_result(
                    canvas_item.key,
                    object_type.value,
                    ImportStatus.SKIPPED.value,
                    f"跳过已存在的{object_type.value}",
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
                    f"覆盖已存在的{object_type.value}",
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
                    f"重命名为 {new_name}",
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
                f"新建{object_type.value}",
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
                ns_key
                for ds_item in self.doc.datasources
                for ns_key in ds_item.namespace_keys
                if ns_key not in self.namespace_key_to_id
            }
            self.namespace_key_to_id.update(
                NameSpace.objects.filter(name__in=namespace_keys).values_list("name", "id")
            )
            tag_names = {tag_name for ds_item in self.doc.datasources for tag_name in ds_item.tags}
            self.tag_name_to_id.update(
                DataSourceTag.objects.filter(name__in=tag_names).values_list("name", "id")
            )
            for ds_item in self.doc.datasources:
                ds_id = self._import_datasource(ds_item)
                if ds_id:
                    self.datasource_key_to_id[ds_item.key] = ds_id

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
