"""配置采集插件说明文档解析。"""

from pathlib import Path

from django.conf import settings

from apps.cmdb.collect.extensions import get_collect_enterprise_extension

DOCUMENT_NOT_FOUND = "未找到对应的文档！"


def _document_directories():
    enterprise_dirs = get_collect_enterprise_extension().doc_dirs
    community_dir = Path(settings.BASE_DIR) / "apps/cmdb/support-files/plugins_doc"
    return [*(Path(item) for item in enterprise_dirs), community_dir]


def get_collect_model_document(model_id: str) -> str:
    """企业文档优先，缺失时回退社区文档。"""
    for directory in _document_directories():
        template_dir = directory.resolve()
        file_path = (template_dir / f"{model_id}.md").resolve()
        if template_dir not in file_path.parents:
            continue
        if file_path.is_file():
            return file_path.read_text(encoding="utf-8")
    return DOCUMENT_NOT_FOUND
