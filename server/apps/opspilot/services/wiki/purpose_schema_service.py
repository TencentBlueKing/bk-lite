"""Wiki 知识库的 Purpose / Schema 模板与 AI 辅助生成。

Purpose 描述目标/范围/关键问题/成功标准;Schema 描述知识类型/字段/正文约定/命名/关系/冲突处理。
两者以 Markdown 为唯一事实来源。AI 辅助根据模板 + 用户描述生成草稿,失败时回退到模板骨架。
"""

import logging

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.models import LLMModel

logger = logging.getLogger("opspilot")

_PURPOSE_SKELETON = """# Purpose

## 目标
{{description}}

## 范围
- 收录:
- 不收录:

## 关键问题
1.

## 成功标准
-
"""

_TEMPLATES = {
    "ops_qa": {
        "name": "运维知识问答",
        "description": "面向运维问答场景,沉淀可复用的问题与解决方案。",
        "purpose_md": _PURPOSE_SKELETON,
        "schema_md": """# Schema

## 知识类型
- 问答(question/answer/适用范围)
- 概念(定义/要点)
- 操作步骤(前置条件/步骤/校验)

## 命名
- 标题用简洁短语,kebab 风格 slug。

## 关系
- 问答可引用概念与操作步骤。

## 冲突处理
- 同一问题出现不同答案时,保留并标注适用条件,进入检查。
""",
    },
    "fault_diagnosis": {
        "name": "故障诊断",
        "description": "沉淀故障现象、根因与处置,支持快速定位。",
        "purpose_md": _PURPOSE_SKELETON,
        "schema_md": """# Schema

## 知识类型
- 故障案例(现象/影响/根因/处置/复盘)
- 根因(描述/触发条件)
- 处置预案(步骤/回滚)

## 关系
- 故障案例关联根因与处置预案。

## 冲突处理
- 同现象多根因时并列保留,标注判别依据。
""",
    },
    "operation_guide": {
        "name": "操作指导",
        "description": "标准化操作手册与最佳实践。",
        "purpose_md": _PURPOSE_SKELETON,
        "schema_md": """# Schema

## 知识类型
- 操作指南(目标/前置/步骤/校验/风险)
- 最佳实践(建议/反例)

## 关系
- 操作指南可引用最佳实践与概念。

## 冲突处理
- 步骤差异保留版本上下文,过期内容进入检查。
""",
    },
    "product_support": {
        "name": "产品支持",
        "description": "产品功能、配置与常见问题支持知识。",
        "purpose_md": _PURPOSE_SKELETON,
        "schema_md": """# Schema

## 知识类型
- 功能说明(用途/配置/限制)
- 常见问题(问题/解答)
- 版本变更(版本/变更点)

## 关系
- 常见问题关联功能说明。

## 冲突处理
- 跨版本差异按版本标注,旧版本进入过期检查。
""",
    },
    "general": {
        "name": "通用知识库",
        "description": "通用结构化知识,适配多数场景。",
        "purpose_md": _PURPOSE_SKELETON,
        "schema_md": """# Schema

## 知识类型
- 概念(定义/要点)
- 实体(属性/关系)
- 主题综述(概述/要点)

## 命名
- 标题用名词短语。

## 关系
- 页面之间用引用建立关联。

## 冲突处理
- 冲突信息保留多观点并进入检查。
""",
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
