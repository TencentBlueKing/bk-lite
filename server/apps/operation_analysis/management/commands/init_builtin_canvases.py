# -- coding: utf-8 --
"""
内置画布初始化命令

从 support-files/builtin_canvases.yaml 读取内置画布定义，
复用 ImportService 执行导入，导入后将画布标记为内置对象并放入内置目录。

- YAML 文件不存在或为空时静默跳过
- 命名空间/数据源冲突策略为 skip（复用已有）
- 画布冲突策略为 skip（用户同名画布优先保留，内置不覆盖）
- 导入前先删除旧内置画布，避免 ImportService 按 name 匹配到旧内置
- 内置目录和内置对象只属于 Default 组织、只读
"""

import os

import yaml
from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction

from apps.core.logger import operation_analysis_logger as logger

BUILTIN_DIRECTORY_KEY = "__builtin__"
BUILTIN_DIRECTORY_NAME = "内置目录"
YAML_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "support-files",
    "builtin_canvases.yaml",
)
MERGEABLE_SECTIONS = ("dashboards", "topologies", "architectures", "datasources", "namespaces")


def _get_default_group_ids():
    """获取 Default 组织 ID（内置对象只属于 Default 组织）"""
    from apps.operation_analysis.management.commands.init_default_groups import get_default_group_id

    return get_default_group_id()


def _get_or_create_builtin_directory(groups):
    """获取或创建内置目录"""
    from apps.operation_analysis.models.models import Directory

    directory = Directory.objects.filter(build_in_key=BUILTIN_DIRECTORY_KEY).first()
    if directory:
        # 更新组织可见性
        if set(directory.groups or []) != set(groups):
            directory.groups = groups
            directory.save(update_fields=["groups"])
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


def _build_conflict_decisions(doc):
    """
    构建冲突决策：全部 skip。
    - namespace/datasource：复用已有
    - canvas（dashboard/topology/architecture）：保护用户同名画布不被覆盖
      导入前已删除旧内置画布，所以 ImportService 只会匹配到用户同名画布（此时 skip 保护用户数据）
    """
    decisions = {}
    for ns in doc.namespaces:
        decisions[ns.key] = "skip"
    for ds in doc.datasources:
        decisions[ds.key] = "skip"
    for db in doc.dashboards:
        decisions[db.key] = "skip"
    for tp in doc.topologies:
        decisions[tp.key] = "skip"
    for ar in doc.architectures:
        decisions[ar.key] = "skip"
    return decisions


def _get_builtin_canvas_file_paths():
    extra_files = getattr(settings, "OPERATION_ANALYSIS_BUILTIN_CANVAS_FILES", []) or []
    if isinstance(extra_files, (str, os.PathLike)):
        extra_files = [extra_files]

    paths = [YAML_FILE_PATH]
    paths.extend(str(path) for path in extra_files if str(path).strip())
    return paths


def _merge_yaml_documents(documents):
    merged = {
        "meta": {
            "schema_version": "1.0.0",
            "exported_at": "",
            "source": {"organization_id": 0},
            "object_counts": {},
        }
    }
    for section in MERGEABLE_SECTIONS:
        merged[section] = []

    for data in documents:
        for section in MERGEABLE_SECTIONS:
            existing_keys = {item.get("key") for item in merged[section] if isinstance(item, dict)}
            for item in data.get(section) or []:
                if isinstance(item, dict) and item.get("key") in existing_keys:
                    continue
                merged[section].append(item)
                if isinstance(item, dict):
                    existing_keys.add(item.get("key"))

    merged["meta"]["object_counts"] = {section: len(merged[section]) for section in MERGEABLE_SECTIONS}
    return merged


class Command(BaseCommand):
    help = "从 YAML 文件导入内置画布（仪表盘/拓扑/架构图）"

    def handle(self, *args, **options):
        # 1. 读取 YAML 文件
        yaml_documents = []
        for file_path in _get_builtin_canvas_file_paths():
            if not os.path.isfile(file_path):
                self.stdout.write(self.style.WARNING(f"内置画布 YAML 文件不存在，跳过: {file_path}"))
                continue

            with open(file_path, "r", encoding="utf-8") as f:
                raw_content = f.read()

            if not raw_content.strip():
                self.stdout.write(self.style.WARNING(f"内置画布 YAML 文件为空，跳过: {file_path}"))
                continue

            data = yaml.safe_load(raw_content)
            if not data:
                self.stdout.write(self.style.WARNING(f"内置画布 YAML 解析结果为空，跳过: {file_path}"))
                continue
            yaml_documents.append(data)

        if not yaml_documents:
            self.stdout.write(self.style.WARNING("内置画布 YAML 无可导入内容，跳过"))
            return

        # 2. 延迟导入（避免循环依赖）
        from apps.operation_analysis.models.models import Architecture, Dashboard, Topology
        from apps.operation_analysis.schemas.import_export_schema import YAMLDocument
        from apps.operation_analysis.services.import_export.import_service import ImportService

        # 3. 解析 YAML 为 YAMLDocument
        try:
            doc = YAMLDocument(**_merge_yaml_documents(yaml_documents))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"内置画布 YAML 解析失败: {e}"))
            logger.error(f"内置画布 YAML 解析失败: {e}")
            return

        total_canvases = len(doc.dashboards) + len(doc.topologies) + len(doc.architectures)
        if total_canvases == 0 and len(doc.namespaces) == 0 and len(doc.datasources) == 0:
            self.stdout.write(self.style.WARNING("内置画布 YAML 中无可导入对象，跳过"))
            return

        # 4. 准备环境
        groups = _get_default_group_ids()
        builtin_dir = _get_or_create_builtin_directory(groups)
        conflict_decisions = _build_conflict_decisions(doc)

        self.stdout.write(
            f"开始导入内置画布: "
            f"{len(doc.namespaces)} 命名空间, "
            f"{len(doc.datasources)} 数据源, "
            f"{len(doc.dashboards)} 仪表盘, "
            f"{len(doc.topologies)} 拓扑图, "
            f"{len(doc.architectures)} 架构图"
        )

        # 5~8 在同一事务中：删旧内置 → 导入 → 标记新内置
        #     如果导入失败，整个事务回滚（包括删除），避免旧内置丢失
        try:
            with transaction.atomic():
                # 5. 先删除旧内置画布（这样 ImportService 不会按 name 匹配到旧内置，
                #    只会匹配用户同名画布 → skip 保护用户数据）
                for model in (Dashboard, Topology, Architecture):
                    deleted_count, _ = model.objects.filter(is_build_in=True).delete()
                    if deleted_count:
                        self.stdout.write(f"清理旧内置 {model.__name__}: {deleted_count} 个")

                # 6. 调用 ImportService 执行导入
                import_service = ImportService(
                    doc=doc,
                    target_directory_id=builtin_dir.id,
                    conflict_decisions=conflict_decisions,
                    secret_supplements={},
                    created_by="system",
                    updated_by="system",
                    groups=groups,
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
                    logger.error(f"内置画布导入失败: {result['summary']}")
                    raise RuntimeError("内置画布导入失败，回滚事务")

                # 7. 将导入成功的画布对象标记为内置
                canvas_type_model_map = {
                    "dashboard": Dashboard,
                    "topology": Topology,
                    "architecture": Architecture,
                }

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
                    if status != "success":
                        continue

                    model = canvas_type_model_map[obj_type]
                    model.objects.filter(id=new_id).update(
                        is_build_in=True,
                        build_in_key=obj_key,
                        directory=builtin_dir,
                    )
                    marked_count += 1

        except RuntimeError:
            # 导入失败，事务已回滚，旧内置画布恢复
            return

        self.stdout.write(self.style.SUCCESS(f"内置画布导入完成: {result['summary']}, 标记 {marked_count} 个内置对象"))
        logger.info(f"内置画布导入完成: {result['summary']}, 标记 {marked_count} 个内置对象")
