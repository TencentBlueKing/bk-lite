"""Wiki 知识库冻结目录骨架。

结构固定为五个知识根加资料根「来源」。模板 / Purpose / Schema 生成已下线；
`get_template_structure` 仍按原入口返回这份唯一骨架，供 bootstrap 与回填复用。
"""

from copy import deepcopy
from typing import Optional

import unicodedata


def normalize_folder_name(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()


def _directory(key, name, page_type, description, parent_key=None, *, default=True, accepts_pages=True):
    allowed = [page_type] if page_type else []
    defaults = [page_type] if default and page_type else []
    return {
        "key": key,
        "name": name,
        "description": description,
        "parent_key": parent_key,
        "order": 10,
        "accepts_pages": accepts_pages,
        "rules": {
            "allowed_page_types": allowed,
            "default_for_page_types": defaults,
        },
    }


def _structure(*directories):
    page_types = []
    seen = set()
    for directory in directories:
        for page_type in directory["rules"]["allowed_page_types"]:
            if page_type in seen:
                continue
            seen.add(page_type)
            page_types.append(page_type)
    return {
        "format_version": 1,
        "page_types": page_types,
        "directories": [
            {
                **directory,
                "order": (index + 1) * 10,
            }
            for index, directory in enumerate(directories)
        ],
    }


FROZEN_KNOWLEDGE_ROOTS = (
    {
        "key": "schema_entity",
        "name": "实体",
        "page_type": "entity",
        "description": "产品、平台、组件、系统、组织、数据集等稳定命名对象",
        "accepts_pages": True,
    },
    {
        "key": "schema_concept",
        "name": "概念",
        "page_type": "concept",
        "description": "架构、机制、流程、依赖关系、方法和其他可复用抽象主题",
        "accepts_pages": True,
    },
    {
        "key": "schema_query",
        "name": "待研究问题",
        "page_type": "query",
        "description": "资料明确提出但没有给出答案、需要后续补充证据的问题",
        "accepts_pages": True,
    },
    {
        "key": "schema_comparison",
        "name": "对比",
        "page_type": "comparison",
        "description": "资料中具有共同维度和明确事实依据的对象对比",
        "accepts_pages": True,
    },
    {
        "key": "schema_synthesis",
        "name": "综合",
        "page_type": "synthesis",
        "description": "跨主题或多来源证据支持的综合结论和适用边界",
        "accepts_pages": True,
    },
)

MATERIALS_ROOT = {
    "key": "schema_source",
    "name": "来源",
    "page_type": None,
    "description": "原始资料与解析预览，不存放知识页",
    "accepts_pages": False,
}

FROZEN_ROOTS = (*FROZEN_KNOWLEDGE_ROOTS, MATERIALS_ROOT)
FROZEN_ROOT_KEYS = frozenset(item["key"] for item in FROZEN_ROOTS)
FROZEN_ROOT_BY_KEY = {item["key"]: item for item in FROZEN_ROOTS}
MATERIALS_ROOT_KEY = MATERIALS_ROOT["key"]
MATERIALS_ROOT_IMPORT_NAME = "来源(导入)"
FROZEN_PAGE_TYPES = tuple(item["page_type"] for item in FROZEN_KNOWLEDGE_ROOTS)
DEFAULT_TEMPLATE_KEY = "general"

_FROZEN_KNOWLEDGE_BY_NAME = {normalize_folder_name(item["name"]): item for item in FROZEN_KNOWLEDGE_ROOTS}
_MATERIALS_ROOT_NAME = normalize_folder_name(MATERIALS_ROOT["name"])

_FROZEN_STRUCTURE = _structure(
    *(
        _directory(
            item["key"],
            item["name"],
            item["page_type"],
            item["description"],
            accepts_pages=item["accepts_pages"],
        )
        for item in FROZEN_ROOTS
    )
)


def match_frozen_knowledge_root_name(name: str) -> Optional[dict]:
    """按显示名对齐知识根。英文 entity 等不视为同名；「来源」不算知识根。"""

    return _FROZEN_KNOWLEDGE_BY_NAME.get(normalize_folder_name(name))


def is_materials_root_name(name: str) -> bool:
    return normalize_folder_name(name) == _MATERIALS_ROOT_NAME


def import_folder_display_name(name: str, *, parent_is_root: bool) -> str:
    """根上的「来源」不能与资料根同名并列，改落到普通知识目录。"""

    if parent_is_root and is_materials_root_name(name):
        return MATERIALS_ROOT_IMPORT_NAME
    return name


def is_frozen_root_name(name: str) -> bool:
    return match_frozen_knowledge_root_name(name) is not None or is_materials_root_name(name)


def get_frozen_structure():
    return deepcopy(_FROZEN_STRUCTURE)


def get_template_structure(template_key):
    """兼容原入口：任意 template_key 都返回同一份冻结骨架。"""

    return get_frozen_structure()
