"""Wiki 知识库的 Purpose / Schema 模板与 AI 辅助生成。

Purpose 描述目标/范围/关键问题/成功标准；结构化模板定义知识类型、目录层级与归类规则，
并作为构建使用的机器真相。兼容的 Schema Markdown 仅保留说明性模板内容；AI 辅助根据模板
+ 用户描述生成说明草稿，失败时回退到模板骨架。
"""

import logging
from copy import deepcopy

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.models import LLMModel

logger = logging.getLogger("opspilot")


def _directory(key, name, page_type, description):
    return {
        "key": key,
        "name": name,
        "description": description,
        "parent_key": None,
        "order": 10,
        "rules": {
            "allowed_page_types": [page_type],
            "default_for_page_types": [page_type],
        },
    }


def _structure(*directories):
    return {
        "format_version": 1,
        "page_types": [directory["rules"]["allowed_page_types"][0] for directory in directories],
        "directories": [
            {
                **directory,
                "order": (index + 1) * 10,
            }
            for index, directory in enumerate(directories)
        ],
    }


# 标题整体降一级(#→##、##→###)，避免设置页 Markdown 预览字号过大。
_PURPOSE_SKELETON = """## Purpose

### 目标
{{description}}

### 范围
- 收录:
- 不收录:

### 关键问题
1.

### 成功标准
-
"""

_TEMPLATES = {
    "ops_qa": {
        "name": "运维知识问答",
        "description": "面向运维问答场景,沉淀可复用的问题与解决方案。",
        "purpose_md": _PURPOSE_SKELETON,
        "schema_md": """## Schema

### 知识类型
- 问答 (`question`: 问题/答案/适用范围)
- 概念 (`concept`: 定义/要点)
- 操作步骤 (`procedure`: 前置条件/步骤/校验)

### 命名
- 标题用简洁短语,kebab 风格 slug。

### 关系
- 问答可引用概念与操作步骤。

### 冲突处理
- 同一问题出现不同答案时,保留并标注适用条件,进入检查。
""",
        "structure": _structure(
            _directory("schema_question", "问答", "question", "问题、答案和适用范围"),
            _directory("schema_concept", "概念", "concept", "概念定义和核心要点"),
            _directory("schema_procedure", "操作步骤", "procedure", "操作前置条件、步骤和校验"),
        ),
    },
    "fault_diagnosis": {
        "name": "故障诊断",
        "description": "沉淀故障现象、根因与处置,支持快速定位。",
        "purpose_md": _PURPOSE_SKELETON,
        "schema_md": """## Schema

### 知识类型
- 故障案例 (`incident`: 现象/影响/根因/处置/复盘)
- 根因 (`root_cause`: 描述/触发条件)
- 处置预案 (`runbook`: 步骤/回滚)

### 关系
- 故障案例关联根因与处置预案。

### 冲突处理
- 同现象多根因时并列保留,标注判别依据。
""",
        "structure": _structure(
            _directory("schema_incident", "故障案例", "incident", "故障现象、影响、根因、处置和复盘"),
            _directory("schema_root_cause", "根因", "root_cause", "根因描述和触发条件"),
            _directory("schema_runbook", "处置预案", "runbook", "故障处置步骤和回滚方案"),
        ),
    },
    "operation_guide": {
        "name": "操作指导",
        "description": "标准化操作手册与最佳实践。",
        "purpose_md": _PURPOSE_SKELETON,
        "schema_md": """## Schema

### 知识类型
- 操作指南 (`guide`: 目标/前置/步骤/校验/风险)
- 最佳实践 (`best_practice`: 建议/反例)

### 关系
- 操作指南可引用最佳实践与概念。

### 冲突处理
- 步骤差异保留版本上下文,过期内容进入检查。
""",
        "structure": _structure(
            _directory("schema_guide", "操作指南", "guide", "操作目标、前置条件、步骤、校验和风险"),
            _directory("schema_best_practice", "最佳实践", "best_practice", "推荐实践、建议和反例"),
        ),
    },
    "product_support": {
        "name": "产品支持",
        "description": "产品功能、配置与常见问题支持知识。",
        "purpose_md": _PURPOSE_SKELETON,
        "schema_md": """## Schema

### 知识类型
- 功能说明 (`feature`: 用途/配置/限制)
- 常见问题 (`faq`: 问题/解答)
- 版本变更 (`release_note`: 版本/变更点)

### 关系
- 常见问题关联功能说明。

### 冲突处理
- 跨版本差异按版本标注,旧版本进入过期检查。
""",
        "structure": _structure(
            _directory("schema_feature", "功能说明", "feature", "产品功能用途、配置和限制"),
            _directory("schema_faq", "常见问题", "faq", "产品常见问题和解答"),
            _directory("schema_release_note", "版本变更", "release_note", "产品版本及其变更内容"),
        ),
    },
    "general": {
        "name": "通用知识库",
        "description": "通用结构化知识,适配多数场景。",
        "purpose_md": _PURPOSE_SKELETON,
        "schema_md": """## Schema

### 知识类型
- 实体 (`entity`: 定义/核心能力/依赖/体系角色)
- 概念 (`concept`: 定义/机制/架构或关系/边界)
- 来源 (`source`: 一份资料一个摘要/覆盖范围/信息缺口)
- 待研究问题 (`query`: 资料明确提出但尚未解决的问题)
- 对比 (`comparison`: 有明确证据和共同维度的对象对比)
- 综合 (`synthesis`: 多主题或多来源证据支持的综合结论)

### 命名
- 标题用名词短语。

### 关系
- 页面之间用 `[[页面标题]]` 建立关联。
- Index 与 Overview 由系统按 Generation 派生，不作为普通知识页面生成。

### 冲突处理
- 冲突信息保留多观点并进入检查。
""",
        "structure": _structure(
            _directory(
                "schema_entity",
                "实体",
                "entity",
                "产品、平台、组件、系统、组织、数据集等稳定命名对象",
            ),
            _directory(
                "schema_concept",
                "概念",
                "concept",
                "架构、机制、流程、依赖关系、方法和其他可复用抽象主题",
            ),
            _directory(
                "schema_source",
                "来源",
                "source",
                "每份资料的内容摘要、覆盖范围、信息质量和已知缺口",
            ),
            _directory(
                "schema_query",
                "待研究问题",
                "query",
                "资料明确提出但没有给出答案、需要后续补充证据的问题",
            ),
            _directory(
                "schema_comparison",
                "对比",
                "comparison",
                "资料中具有共同维度和明确事实依据的对象对比",
            ),
            _directory(
                "schema_synthesis",
                "综合",
                "synthesis",
                "跨主题或多来源证据支持的综合结论和适用边界",
            ),
        ),
    },
}


def list_templates():
    """返回模板元数据 + 固定正文骨架(供前端选模板后直接填充,用户再编辑)。"""
    return [
        {
            "key": key,
            "name": tpl["name"],
            "description": tpl["description"],
            "purpose_md": tpl["purpose_md"],
            "schema_md": tpl["schema_md"],
        }
        for key, tpl in _TEMPLATES.items()
    ]


def _get_template(template_key):
    return _TEMPLATES.get(template_key) or _TEMPLATES["general"]


def get_template_structure(template_key):
    """返回模板的结构化目录骨架，调用方可安全修改返回值。"""

    return deepcopy(_get_template(template_key)["structure"])


def _fallback(template, description):
    purpose = template["purpose_md"].replace("{{description}}", (description or "").strip())
    return purpose, template["schema_md"]


def _parse_llm_output(content):
    """解析 ===PURPOSE=== / ===SCHEMA=== 两段输出;解析不出则抛错由上层回退。"""
    upper = content
    if "===SCHEMA===" not in upper or "===PURPOSE===" not in upper:
        raise ValueError("LLM output missing PURPOSE/SCHEMA markers")
    after_purpose = upper.split("===PURPOSE===", 1)[1]
    purpose_part, schema_part = after_purpose.split("===SCHEMA===", 1)
    purpose = purpose_part.strip()
    schema = schema_part.strip()
    if not purpose or not schema:
        raise ValueError("LLM output empty PURPOSE/SCHEMA")
    return purpose, schema


def _llm_generate(template, description, llm_model_id):
    """有 llm_model_id 时调用 LLM 生成;无或失败时回退到模板骨架。"""
    if not llm_model_id:
        return _fallback(template, description)
    try:
        llm = LLMModel.objects.get(id=llm_model_id)
        prompt = (
            "你是企业知识库设计助手。请根据下面的模板骨架和用户描述,生成该知识库的 Purpose 与 Schema(Markdown)。\n"
            "严格按如下格式输出,不要多余内容:\n"
            "===PURPOSE===\n<Purpose markdown>\n===SCHEMA===\n<Schema markdown>\n\n"
            f"# 用户描述\n{(description or '').strip()}\n\n"
            f"# Purpose 模板骨架\n{template['purpose_md']}\n\n"
            f"# Schema 模板骨架\n{template['schema_md']}\n"
        )
        request = BasicLLMRequest(
            openai_api_base=llm.openai_api_base,
            openai_api_key=llm.openai_api_key,
            model=llm.model_name,
            temperature=0.3,
            user_message=prompt,
        )
        content = LLMClientFactory.invoke_isolated(request, [{"role": "user", "content": prompt}])
        return _parse_llm_output(content)
    except Exception:
        logger.exception("wiki purpose/schema LLM 生成失败,回退到模板骨架")
        return _fallback(template, description)


def generate_purpose_schema(template_key, description, llm_model_id):
    """根据模板 + 描述生成 (purpose_md, schema_md)。"""
    template = _get_template(template_key)
    return _llm_generate(template, description, llm_model_id)
