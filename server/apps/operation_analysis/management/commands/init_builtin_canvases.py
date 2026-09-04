# -- coding: utf-8 --
"""
内置画布初始化命令

合并 source_api.json、support-files/builtin_canvases.yaml 与
support-files/flow_dashboard.yaml 中的内置定义，
复用 ImportService 在一个事务中同步数据源和画布。

- YAML 文件不存在或为空时静默跳过
- 命名空间冲突复用已有对象，内置数据源按稳定 key 覆盖更新
- 内置画布按 build_in_key 原位同步，保留主键和组织可见性
- 新增画布遇到用户同名对象时跳过，避免覆盖用户数据
- 新建内置对象默认属于 Default 组织；存量 groups 作为运营配置保留
"""

import os

import yaml
from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction

from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.common.load_json_data import load_support_json
from apps.operation_analysis.constants.import_export import YAML_SCHEMA_VERSION

BUILTIN_DIRECTORY_KEY = "__builtin__"
BUILTIN_DIRECTORY_NAME = "内置目录"
YAML_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "support-files",
    "builtin_canvases.yaml",
)
FLOW_DASHBOARD_YAML_PATH = os.path.join(
    os.path.dirname(YAML_FILE_PATH),
    "flow_dashboard.yaml",
)
MERGEABLE_SECTIONS = ("dashboards", "topologies", "architectures", "screens", "reports", "datasources", "namespaces")
DEFAULT_RETIRE_LIMIT = 200


def _get_default_group_ids():
    """获取 Default 组织 ID（内置对象只属于 Default 组织）"""
    from apps.operation_analysis.management.commands.init_default_groups import get_default_group_id

    return get_default_group_id()


def _get_or_create_builtin_directory(groups):
    """获取或创建内置目录"""
    from apps.operation_analysis.models.models import Directory

    directory = Directory.objects.filter(build_in_key=BUILTIN_DIRECTORY_KEY).first()
    if directory:
        return directory

    # 处理同名目录冲突（name+parent 有唯一约束，parent=None）
    existing_by_name = Directory.objects.filter(name=BUILTIN_DIRECTORY_NAME, parent=None).first()
    if existing_by_name:
        # 已有同名根目录但非内置，标记为内置
        existing_by_name.is_build_in = True
        existing_by_name.build_in_key = BUILTIN_DIRECTORY_KEY
        existing_by_name.groups = groups
        existing_by_name.save(update_fields=["is_build_in", "build_in_key", "groups"])
        return existing_by_name

    directory = Directory.objects.create(
        name=BUILTIN_DIRECTORY_NAME,
        parent=None,
        is_active=True,
        is_build_in=True,
        build_in_key=BUILTIN_DIRECTORY_KEY,
        groups=groups,
        created_by="system",
        updated_by="system",
    )
    return directory


def _iter_canvas_sections(doc):
    return (
        ("dashboard", doc.dashboards),
        ("topology", doc.topologies),
        ("architecture", doc.architectures),
        ("screen", doc.screens),
        ("report", doc.reports),
    )


def _build_conflict_decisions(doc, existing_canvas_ids=None):
    """
    构建冲突决策。
    - namespace：复用已有
    - datasource：系统内置定义覆盖更新
    - 已按稳定键识别的内置 canvas：原位覆盖内容
    - 新增 canvas：同名用户画布存在时跳过，避免覆盖用户数据
    """
    decisions = {}
    for ns in doc.namespaces:
        decisions[ns.key] = "skip"
    for ds in doc.datasources:
        decisions[ds.key] = "overwrite"
    existing_canvas_ids = existing_canvas_ids or {}
    for object_type, items in _iter_canvas_sections(doc):
        for item in items:
            decisions[item.key] = "overwrite" if (object_type, item.key) in existing_canvas_ids else "skip"
    return decisions


def _get_existing_builtin_canvas_ids(doc, canvas_type_model_map):
    existing_canvas_ids = {}
    for object_type, items in _iter_canvas_sections(doc):
        keys = [item.key for item in items]
        if not keys:
            continue
        model = canvas_type_model_map[object_type]
        rows = model.objects.select_for_update().filter(is_build_in=True, build_in_key__in=keys).values_list("build_in_key", "id")
        existing_canvas_ids.update({(object_type, build_in_key): object_id for build_in_key, object_id in rows})
        for item in items:
            identity = (object_type, item.key)
            if identity in existing_canvas_ids:
                continue
            legacy = model.objects.select_for_update().filter(is_build_in=True, name=item.name).exclude(build_in_key__in=keys).first()
            if legacy is None:
                continue
            previous_key = legacy.build_in_key
            legacy.build_in_key = item.key
            legacy.save(update_fields=["build_in_key", "updated_at"])
            existing_canvas_ids[identity] = legacy.pk
            logger.warning(
                "[BuiltinCanvas] 按名称认领历史内置%s: id=%s, old_key=%s, new_key=%s",
                object_type,
                legacy.pk,
                previous_key,
                item.key,
            )
    return existing_canvas_ids


def _collect_retired_builtin_objects(doc, canvas_type_model_map, datasource_model, *, lock, limit):
    candidates = []
    for object_type, items in _iter_canvas_sections(doc):
        model = canvas_type_model_map[object_type]
        active_keys = {item.key for item in items}
        queryset = (
            model.objects.filter(is_build_in=True, build_in_key__isnull=False)
            .exclude(build_in_key="")
            .exclude(build_in_key__in=active_keys)
            .order_by("pk")
        )
        if lock:
            queryset = queryset.select_for_update()
        remaining = limit - len(candidates)
        candidates.extend((object_type, instance) for instance in queryset[: remaining + 1])
        if len(candidates) > limit:
            raise RuntimeError(f"待退役内置对象超过安全上限 {limit}，停止清理")

    builtin_keys = {item.key for item in doc.datasources}
    datasource_queryset = (
        datasource_model.objects.filter(is_build_in=True, build_in_key__isnull=False)
        .exclude(build_in_key="")
        .exclude(build_in_key__in=builtin_keys)
        .order_by("pk")
    )
    if lock:
        datasource_queryset = datasource_queryset.select_for_update()
    remaining = limit - len(candidates)
    candidates.extend(("datasource", instance) for instance in datasource_queryset[: remaining + 1])
    if len(candidates) > limit:
        raise RuntimeError(f"待退役内置对象超过安全上限 {limit}，停止清理")
    return candidates


def _write_retirement_plan(candidates, stdout, *, dry_run):
    action = "预检待退役" if dry_run else "清理已退役"
    for object_type, instance in candidates:
        stdout.write(f"{action}内置对象: type={object_type}, id={instance.pk}, " f"build_in_key={instance.build_in_key}, name={instance.name}")
    stdout.write(f"{action}内置对象合计: {len(candidates)} 个")


def _delete_retired_builtin_objects(candidates, stdout):
    from apps.operation_analysis.services.canvas_report.registry import get_canvas_report_adapter

    results = []
    for object_type, instance in candidates:
        instance_id = instance.pk
        build_in_key = instance.build_in_key
        name = instance.name
        if object_type in {"dashboard", "screen", "report"}:
            get_canvas_report_adapter(object_type).terminate_subscriptions_on_delete(
                instance,
                actor="system",
            )
        instance.delete()
        results.append((object_type, instance_id, build_in_key, name))

    def write_results():
        for object_type, instance_id, build_in_key, name in results:
            stdout.write(f"清理已退役内置对象: type={object_type}, id={instance_id}, " f"build_in_key={build_in_key}, name={name}")
        stdout.write(f"清理已退役内置对象合计: {len(results)} 个")

    transaction.on_commit(write_results)


def _get_builtin_canvas_file_paths():
    extra_files = getattr(settings, "OPERATION_ANALYSIS_BUILTIN_CANVAS_FILES", []) or []
    if isinstance(extra_files, (str, os.PathLike)):
        extra_files = [extra_files]

    paths = [YAML_FILE_PATH, FLOW_DASHBOARD_YAML_PATH]
    seen = {os.path.abspath(path) for path in paths}
    for path in extra_files:
        normalized = str(path).strip()
        if not normalized:
            continue
        absolute = os.path.abspath(normalized)
        if absolute in seen:
            continue
        seen.add(absolute)
        paths.append(normalized)
    return paths


def _get_object_counts_error(data):
    meta = data.get("meta") if isinstance(data, dict) else None
    object_counts = meta.get("object_counts") if isinstance(meta, dict) else None
    if not isinstance(object_counts, dict):
        return "缺少 meta.object_counts"

    for section in MERGEABLE_SECTIONS:
        expected = object_counts.get(section)
        if not isinstance(expected, int) or isinstance(expected, bool):
            return f"meta.object_counts.{section} 缺失或不是整数"
        section_items = data.get(section) or []
        if not isinstance(section_items, list):
            return f"{section} 不是数组"
        actual = len(section_items)
        if expected != actual:
            return f"meta.object_counts.{section}={expected}，实际为 {actual}"
    return None


def _merge_yaml_documents(documents):
    merged = {
        "meta": {
            "schema_version": YAML_SCHEMA_VERSION,
            "exported_at": "",
            "source": {"organization_id": 0},
            "object_counts": {},
        }
    }
    for section in MERGEABLE_SECTIONS:
        merged[section] = []

    datasource_defaults = {
        "rest_api": "",
        "source_type": "nats",
        "connection_config": {},
        "query_config": {},
        "desc": "",
        "is_active": True,
        "params": [],
        "tags": [],
        "chart_type": [],
        "field_schema": [],
        "namespace_keys": [],
    }

    def normalize_datasource(item):
        normalized = {"key": item.get("key"), "name": item.get("name")}
        for field, default in datasource_defaults.items():
            value = item.get(field, default)
            normalized[field] = sorted(value) if field in {"tags", "namespace_keys"} else value
        return normalized

    for data in documents:
        for section in MERGEABLE_SECTIONS:
            existing_by_key = {item.get("key"): item for item in merged[section] if isinstance(item, dict)}
            for item in data.get(section) or []:
                if isinstance(item, dict) and item.get("key") in existing_by_key:
                    if section == "datasources" and normalize_datasource(existing_by_key[item.get("key")]) != normalize_datasource(item):
                        raise ValueError(f"内置数据源重复定义不一致: {item.get('key')}")
                    continue
                merged[section].append(item)
                if isinstance(item, dict):
                    existing_by_key[item.get("key")] = item

    merged["meta"]["object_counts"] = {section: len(merged[section]) for section in MERGEABLE_SECTIONS}
    return merged


def _load_source_api_document():
    tag_names = {item["tag_id"]: item["name"] for item in load_support_json("tags.json")}
    datasources = []
    for source in load_support_json("source_api.json"):
        item = dict(source)
        tags = item.pop("tag", [])
        rest_api = item.get("rest_api", "")
        # 显式 key 优先，避免改展示名时拖动稳定身份与画布引用。
        stable_key = item.pop("key", None) or f"{item['name']}::{rest_api}"
        item.update(
            {
                "key": stable_key,
                "tags": [tag_names.get(tag, tag) for tag in tags],
                "namespace_keys": ["默认命名空间"] if item.get("source_type", "nats") == "nats" else [],
            }
        )
        datasources.append(item)
    return {"datasources": datasources}


def _ensure_builtin_tags():
    from apps.operation_analysis.models.datasource_models import DataSourceTag

    for data in load_support_json("tags.json"):
        defaults = dict(data)
        tag_id = defaults.pop("tag_id")
        DataSourceTag.objects.update_or_create(tag_id=tag_id, defaults=defaults)


def _claim_legacy_builtin_datasources(doc):
    from apps.operation_analysis.common.builtin_datasource_identity import find_claimable_datasource
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel

    for item in doc.datasources:
        # 仅按 build_in_key / 精确 (name, rest_api) / key 内历史名认领；禁止只按 rest_api。
        instance = find_claimable_datasource(
            DataSourceAPIModel,
            stable_key=item.key,
            name=item.name,
            rest_api=item.rest_api,
        )
        if not instance:
            continue
        instance.name = item.name
        instance.rest_api = item.rest_api
        instance.is_build_in = True
        instance.build_in_key = item.key
        instance.save(update_fields=["name", "rest_api", "is_build_in", "build_in_key", "updated_at"])


class Command(BaseCommand):
    help = "从 YAML 文件导入内置画布（仪表盘/拓扑/架构图）"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="只预检待退役内置对象，不修改数据库")

    def handle(self, *args, **options):  # noqa: C901
        # 1. 读取 YAML 文件
        try:
            yaml_documents = [_load_source_api_document()]
        except Exception as error:
            self.stdout.write(self.style.ERROR(f"内置数据源定义加载失败，跳过同步: {type(error).__name__}: {error}"))
            logger.error("[BuiltinCanvas] 内置数据源定义加载失败，跳过同步：%s", error, exc_info=True)
            return
        loaded_yaml_count = 0
        definitions_complete = True
        for file_path in _get_builtin_canvas_file_paths():
            if not os.path.isfile(file_path):
                definitions_complete = False
                self.stdout.write(self.style.WARNING(f"内置画布 YAML 文件不存在，跳过: {file_path}"))
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    raw_content = f.read()
            except (OSError, UnicodeError) as error:
                self.stdout.write(self.style.ERROR(f"内置画布 YAML 读取失败，跳过同步: {file_path}: {error}"))
                logger.error("[BuiltinCanvas] 内置画布 YAML 读取失败，跳过同步：%s", file_path, exc_info=True)
                return

            if not raw_content.strip():
                definitions_complete = False
                self.stdout.write(self.style.WARNING(f"内置画布 YAML 文件为空，跳过: {file_path}"))
                continue

            try:
                data = yaml.safe_load(raw_content)
            except yaml.YAMLError as error:
                self.stdout.write(self.style.ERROR(f"内置画布 YAML 解析失败，跳过同步: {file_path}: {type(error).__name__}: {error}"))
                logger.error("[BuiltinCanvas] 内置画布 YAML 解析失败，跳过同步：%s", file_path, exc_info=True)
                return
            if not data:
                definitions_complete = False
                self.stdout.write(self.style.WARNING(f"内置画布 YAML 解析结果为空，跳过: {file_path}"))
                continue
            object_counts_error = _get_object_counts_error(data)
            if object_counts_error:
                definitions_complete = False
                self.stdout.write(self.style.WARNING(f"内置画布 YAML 快照不完整，本次禁止退役清理: {file_path}: {object_counts_error}"))
            yaml_documents.append(data)
            loaded_yaml_count += 1

        if loaded_yaml_count == 0:
            self.stdout.write(self.style.WARNING("内置画布 YAML 无可导入内容，跳过"))
            return

        # 2. 延迟导入（避免循环依赖）
        from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
        from apps.operation_analysis.models.models import Architecture, Dashboard, Report, Screen, Topology
        from apps.operation_analysis.schemas.import_export_schema import YAMLDocument
        from apps.operation_analysis.services.import_export.import_service import ImportService

        # 3. 解析 YAML 为 YAMLDocument
        try:
            doc = YAMLDocument(**_merge_yaml_documents(yaml_documents))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"内置画布 YAML 解析失败: {e}"))
            logger.error("[BuiltinCanvas] 内置画布 YAML 解析失败：%s", e, exc_info=True)
            return

        total_canvases = len(doc.dashboards) + len(doc.topologies) + len(doc.architectures) + len(doc.screens) + len(doc.reports)
        if total_canvases == 0 and len(doc.namespaces) == 0 and len(doc.datasources) == 0:
            self.stdout.write(self.style.WARNING("内置画布 YAML 中无可导入对象，跳过"))
            return

        canvas_type_model_map = {
            "dashboard": Dashboard,
            "topology": Topology,
            "architecture": Architecture,
            "screen": Screen,
            "report": Report,
        }
        try:
            retire_limit = int(getattr(settings, "OPERATION_ANALYSIS_BUILTIN_RETIRE_LIMIT", DEFAULT_RETIRE_LIMIT))
            if retire_limit < 0:
                raise ValueError("退役上限不能小于 0")
        except (TypeError, ValueError) as error:
            self.stdout.write(self.style.ERROR(f"内置对象退役上限无效，跳过同步: {error}"))
            logger.error("[BuiltinCanvas] 内置对象退役上限无效，跳过同步：%s", error, exc_info=True)
            return

        if options.get("dry_run"):
            if not definitions_complete:
                self.stdout.write(self.style.WARNING("内置定义文件不完整，无法预检退役对象"))
                return
            try:
                with transaction.atomic():
                    _claim_legacy_builtin_datasources(doc)
                    _get_existing_builtin_canvas_ids(doc, canvas_type_model_map)
                    candidates = _collect_retired_builtin_objects(
                        doc,
                        canvas_type_model_map,
                        DataSourceAPIModel,
                        lock=True,
                        limit=retire_limit,
                    )
                    _write_retirement_plan(candidates, self.stdout, dry_run=True)
                    transaction.set_rollback(True)
            except Exception as error:
                self.stdout.write(self.style.ERROR(f"内置对象退役预检失败: {type(error).__name__}: {error}"))
                logger.error("[BuiltinCanvas] 内置对象退役预检失败：%s", error, exc_info=True)
                return
            return

        # 4. 准备环境
        try:
            groups = _get_default_group_ids()
        except Exception as error:
            self.stdout.write(self.style.ERROR(f"Default 组织加载失败，跳过内置画布同步: {type(error).__name__}: {error}"))
            logger.error("[BuiltinCanvas] Default 组织加载失败，跳过同步：%s", error, exc_info=True)
            return
        self.stdout.write(
            f"开始导入内置画布: "
            f"{len(doc.namespaces)} 命名空间, "
            f"{len(doc.datasources)} 数据源, "
            f"{len(doc.dashboards)} 仪表盘, "
            f"{len(doc.topologies)} 拓扑图, "
            f"{len(doc.architectures)} 架构图, "
            f"{len(doc.screens)} 大屏, "
            f"{len(doc.reports)} 报表"
        )

        # 5~8 在同一事务中：按稳定键同步 → 标记新内置 → 清理已退役内置
        try:
            with transaction.atomic():
                _claim_legacy_builtin_datasources(doc)
                existing_canvas_ids = _get_existing_builtin_canvas_ids(doc, canvas_type_model_map)
                retired_candidates = []
                if definitions_complete:
                    retired_candidates = _collect_retired_builtin_objects(
                        doc,
                        canvas_type_model_map,
                        DataSourceAPIModel,
                        lock=True,
                        limit=retire_limit,
                    )
                _ensure_builtin_tags()
                builtin_dir = _get_or_create_builtin_directory(groups)

                conflict_decisions = _build_conflict_decisions(doc, existing_canvas_ids)

                # 6. 调用 ImportService 执行导入
                import_service = ImportService(
                    doc=doc,
                    target_directory_id=builtin_dir.id,
                    conflict_decisions=conflict_decisions,
                    secret_supplements={},
                    created_by="system",
                    updated_by="system",
                    groups=groups,
                    existing_canvas_ids=existing_canvas_ids,
                    preserve_existing_canvas_groups=True,
                )

                result = import_service.execute()

                if not result["success"]:
                    # 打印失败详情后回滚整个事务
                    self.stdout.write(self.style.ERROR(f"内置画布导入失败: {result['summary']}"))
                    for item_result in result.get("results", []):
                        status = item_result.get("status", "")
                        if status == "failed":
                            obj_type = item_result.get("object_type", "unknown")
                            obj_key = item_result.get("object_key", "unknown")
                            error = item_result.get("error", "未知错误")
                            self.stdout.write(self.style.ERROR(f"  失败对象: [{obj_type}] {obj_key} - {error}"))
                    logger.error("[BuiltinCanvas] 内置画布导入失败：%s", result["summary"])
                    raise RuntimeError("内置画布导入失败，回滚事务")

                # 7. 将导入成功的画布对象标记为内置
                marked_count = 0
                for item_result in result["results"]:
                    obj_type = item_result["object_type"]
                    new_id = item_result.get("new_id")
                    obj_key = item_result["object_key"]
                    status = item_result["status"]

                    if obj_type not in canvas_type_model_map:
                        continue
                    if not new_id:
                        continue
                    if status not in {"success", "overwritten"}:
                        continue

                    model = canvas_type_model_map[obj_type]
                    model.objects.filter(id=new_id).update(
                        is_build_in=True,
                        build_in_key=obj_key,
                        directory=builtin_dir,
                    )
                    marked_count += 1

                if definitions_complete:
                    _delete_retired_builtin_objects(retired_candidates, self.stdout)
                else:
                    self.stdout.write(self.style.WARNING("内置定义文件不完整，本次跳过已退役画布与数据源清理"))

                for item in doc.datasources:
                    DataSourceAPIModel.objects.filter(name=item.name, rest_api=item.rest_api).update(
                        is_build_in=True,
                        build_in_key=item.key,
                        updated_by="system",
                    )

        except Exception as error:
            # 非关键本地初始化保持 fail-open；事务已回滚，不留下半更新。
            self.stdout.write(self.style.ERROR(f"内置画布与数据源同步失败，已回滚: {type(error).__name__}: {error}"))
            logger.error("[BuiltinCanvas] 内置画布与数据源同步失败，已回滚：%s", error, exc_info=True)
            return

        self.stdout.write(self.style.SUCCESS(f"内置画布导入完成: {result['summary']}, 标记 {marked_count} 个内置对象"))
        logger.info("[BuiltinCanvas] 内置画布导入完成：%s，标记 %s 个内置对象", result["summary"], marked_count)
