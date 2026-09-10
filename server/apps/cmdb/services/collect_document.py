"""配置采集插件说明文档解析。"""

from pathlib import Path

from django.conf import settings

from apps.cmdb.collect.extensions import get_collect_enterprise_extension
from apps.cmdb.language.service import SettingLanguage, normalize_cmdb_language

DOCUMENT_NOT_FOUND = "未找到对应的文档！"


def _document_directories():
    enterprise_dirs = get_collect_enterprise_extension().doc_dirs
    community_dir = Path(settings.BASE_DIR) / "apps/cmdb/support-files/plugins_doc"
    return [*(Path(item) for item in enterprise_dirs), community_dir]


def _document_filenames(model_id: str, language: str | None):
    if normalize_cmdb_language(language) == "en":
        return [f"{model_id}.en.md", f"{model_id}.md"]
    return [f"{model_id}.md"]


def get_collect_model_document(model_id: str, language: str | None = None) -> str:
    """企业文档优先，缺失时回退社区文档；英文优先读 .en.md。"""
    for directory in _document_directories():
        template_dir = Path(directory).resolve()
        for filename in _document_filenames(model_id, language):
            file_path = (template_dir / filename).resolve()
            if template_dir not in file_path.parents:
                continue
            if file_path.is_file():
                return file_path.read_text(encoding="utf-8")
    translated = SettingLanguage(language).get_val("COLLECT", "DOCUMENT_NOT_FOUND")
    return translated or DOCUMENT_NOT_FOUND
