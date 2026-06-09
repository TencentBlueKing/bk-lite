## Context

LLMSkill 当前的 `skill_prompt` 是纯文本字段，用户在其中直接编写 prompt。当需要使用 browser_use 等工具登录网站时，账号密码只能明文写入 prompt，在 API 返回、前端展示、日志中均会暴露。

现有的 `tools` 字段已有一套密码加密模式（`tools[].kwargs[]` 中 `type=password` 的值通过 `EncryptMixin` 加密），本次设计复用该模式，为 `skill_prompt` 增加参数化能力。

## Goals / Non-Goals

**Goals:**
- 用户可为 LLMSkill 定义 prompt 参数（key/value/type），在 prompt 中用 `{{key}}` 引用
- `type=password` 的参数值加密存储，API 读取时掩码返回 `"******"`
- 执行时自动将 `{{key}}` 替换为真实值（解密后），替换发生在 prompt 进入下游模板引擎之前
- 覆盖所有 LLMSkill 执行路径：直接执行 + 工作流 AgentNode

**Non-Goals:**
- 意图分类节点（IntentClassifierNode）不涉及——它不使用 LLMSkill
- 不做参数嵌套或表达式语法，仅支持简单的 `{{key}}` 替换
- 不做参数的版本管理或审计日志

## Decisions

### 1. 模板语法：使用 `{{key}}`

**选择**: `{{key}}`

**备选方案**:
- `${key}` — shell 风格，与 JavaScript 模板字面量冲突
- `<<key>>` — 不直观，增加用户学习成本
- `{%key%}` — Jinja2 语句块语法，语义不匹配

**理由**: `{{key}}` 是最广泛使用的模板变量语法（Mustache/Vue/Jinja2 变量），用户零学习成本。潜在的模板引擎冲突通过**替换时机**解决（见决策 #2），无需换语法。

### 2. 替换时机：进入模板引擎之前

**选择**: 在 `skill_prompt` 被赋值到 `chat_kwargs["system_message_prompt"]` 之前，先完成 `{{key}}` → 真实值的替换。

```
skill_prompt (含 {{key}})
        │
        ▼
  resolve_skill_params()   ← 新增：解密 + 字符串替换
        │
        ▼
skill_prompt (纯文本，无变量)
        │
        ▼
chat_kwargs["system_message_prompt"]
        │
        ▼
TemplateLoader.render_template()   ← 已有模板引擎，看到的是纯文本
```

**理由**: 替换在最上游完成，下游模板引擎（`node.py` 的 `TemplateLoader`）看到的已经是纯文本，彻底避免语法冲突。

**注入点**:
- 直接执行路径：`chat_service.py` 约第 154 行，`kwargs["skill_prompt"]` 赋值前
- 工作流路径：`agent.py` 的 `_build_llm_params()` 约第 131 行，`skill.skill_prompt` 读取后

### 3. 字段设计：`skill_params` JSONField

**选择**: 在 LLMSkill 模型上新增 `skill_params = JSONField(default=list)`

**数据结构**:
```json
[
  {"key": "username", "value": "admin",       "type": "text"},
  {"key": "password", "value": "<encrypted>", "type": "password"}
]
```

**理由**: 与现有 `tools[].kwargs[]` 结构完全一致，复用同一套加密/解密/掩码逻辑，减少认知负担和维护成本。

### 4. 加密方案：复用 EncryptMixin

**选择**: 直接使用 `EncryptMixin.encrypt_field()` / `decrypt_field()`（Fernet 对称加密，基于 Django SECRET_KEY）。

**理由**: 已有成熟实现且在 tools 密码中验证过，无需引入新依赖。`decrypt_field` 内置了 `InvalidToken` 容错（明文跳过），兼容存量数据。

### 5. 更新时的密码保留策略

**选择**: 后端判断 `type == "password"` 且 `value == "******"` 时，从 DB 原有记录中取回加密值，不做更新。

**流程**:
```
前端 PUT 请求
    │
    ▼
遍历 skill_params:
    ├─ type=text     → 直接存储
    ├─ type=password & value="******" → 从 instance.skill_params 中找同 key 的旧加密值
    └─ type=password & value≠"******" → EncryptMixin.encrypt_field() 加密新值
```

**备选方案**:
- 返回密文让前端原样回传 — 泄露密文，不安全
- 返回空值 + is_encrypted 标记 — 增加前端复杂度

### 6. 替换函数设计：`resolve_skill_params()`

**选择**: 新增一个工具函数，统一处理解密和替换逻辑，供两条执行路径共用。

```python
def resolve_skill_params(skill_prompt: str, skill_params: list) -> str:
    """解密 password 类型参数，将 skill_prompt 中的 {{key}} 替换为真实值"""
    if not skill_params:
        return skill_prompt
    for param in skill_params:
        if param.get("type") == "password":
            EncryptMixin.decrypt_field("value", param)
        key = param.get("key", "")
        value = param.get("value", "")
        skill_prompt = skill_prompt.replace("{{" + key + "}}", str(value))
    return skill_prompt
```

**放置位置**: `server/apps/opspilot/utils/prompt_utils.py`（新文件）或直接放在 `chat_service.py` 中作为静态方法。倾向新建 `prompt_utils.py`，因为两条路径都要用。

### 7. 执行路径覆盖

| 路径 | 文件 | 注入方式 |
|---|---|---|
| 直接执行 | `chat_service.py:154` | `kwargs["skill_prompt"] = resolve_skill_params(kwargs["skill_prompt"], kwargs.get("skill_params", []))` |
| 工作流 AgentNode | `agent.py:131` | 在 `_build_llm_params()` 中读取 `skill.skill_params`，调用 `resolve_skill_params()` 后再赋值 |
| IntentClassifierNode | 不涉及 | 不使用 LLMSkill，prompt 由节点自行构建 |

### 8. Serializer 掩码

在 `LLMSerializer` 中新增 `get_skill_params()` 方法（SerializerMethodField），遍历参数列表，将 `type=password` 的 `value` 替换为 `"******"` 后返回。

### 9. 前端：Skill 设置页新增 Prompt 参数区域

**位置**: `web/src/app/opspilot/(pages)/skill/detail/settings/page.tsx`

**UI 布局**: 在现有 "Prompt" TextArea 下方新增一个 "Prompt 参数" 区域，使用可折叠面板或独立区块。

```
┌─────────────────────────────────────────────┐
│  Prompt                                     │
│  ┌─────────────────────────────────────────┐│
│  │ 登陆 xxx，输入帐号 {{username}}，       ││
│  │ 密码 {{password}}                       ││
│  └─────────────────────────────────────────┘│
│                                             │
│  Prompt 参数                    [+ 添加参数] │
│  ┌──────────┬───────────┬──────┬──────────┐│
│  │ 参数名    │ 值        │ 类型  │ 操作     ││
│  ├──────────┼───────────┼──────┼──────────┤│
│  │ username │ admin     │ text │ [删除]   ││
│  │ password │ ******    │ pass │ [删除]   ││
│  └──────────┴───────────┴──────┴──────────┘│
└─────────────────────────────────────────────┘
```

**实现方式**: 复用 `toolSelector.tsx` 中已有的 `Form.List` + `renderInput()` 模式。

**组件结构**:
- 使用 Ant Design `Form.List name="skill_params"` 动态渲染参数行
- 每行包含: `key`（Input）、`value`（根据 type 切换：text→Input，password→EditablePasswordField）、`type`（Select: text/password）、删除按钮
- 顶部 "添加参数" 按钮，点击添加空行 `{key: "", value: "", type: "text"}`
- type 切换为 password 时，value 输入框变为 `EditablePasswordField`（已有组件 `web/src/components/dynamic-form/editPasswordField.tsx`）

**数据流**:
```
页面加载 (GET skill)
    │
    ▼
API 返回 skill_params（password 值为 "******"）
    │
    ▼
Form 初始化: skill_params 数组 → Form.List 渲染
    │
    ▼
用户编辑 → 点击保存
    │
    ▼
Form 提交: 收集 skill_params 数组（未改动的 password 仍为 "******"）
    │
    ▼
PUT /api/.../llm/<id>/ → 后端处理加密/保留逻辑
```

**前端不做加密**: 加密全部由后端处理，前端只负责：
- 展示：password 类型显示 `EditablePasswordField`（带眼睛切换的密码输入框）
- 新建时：用户输入明文，提交给后端加密
- 编辑时：API 返回 `"******"`，未修改则原样回传

### 10. 前端：执行测试时传递 skill_params

**位置**: `web/src/app/opspilot/(pages)/skill/detail/settings/page.tsx` 的 `handleSendMessage` 函数（约第 180 行）

当用户在右侧聊天面板测试技能时，`handleSendMessage` 构建请求 payload。需要将当前表单中的 `skill_params` 一并传入，使测试执行也能正确替换 `{{key}}`。

```typescript
// handleSendMessage 中新增:
const skillParams = form.getFieldValue('skill_params') || [];
// payload 中加入:
{ ...existingPayload, skill_params: skillParams }
```

**注意**: 测试执行时 password 值为 `"******"`（从 API 返回的掩码值）。后端在执行路径需要处理这种情况——从 DB 中读取真实加密值而非使用前端传来的 `"******"`。这意味着 `chat_service.py` 的执行逻辑应从 DB skill 对象读取 `skill_params`，而非依赖前端传入。

### 11. 前端：国际化

所有新增的 UI 文案需要添加 i18n key：
- "Prompt 参数" / "Prompt Parameters"
- "参数名" / "Parameter Name"
- "值" / "Value"
- "类型" / "Type"
- "添加参数" / "Add Parameter"
- "text" / "password" 类型标签

遵循现有 i18n 文件结构（`web/src/app/opspilot/` 下的 locale 文件）。

## Risks / Trade-offs

**[风险] 未替换的变量残留在 prompt 中** → 如果用户在 prompt 中写了 `{{foo}}` 但 `skill_params` 中没有定义 `foo`，该占位符会原样发送给 LLM。Mitigation: 这是可接受的行为——不做静态校验，用户可在测试执行时发现。后续可在前端添加变量引用检查。

**[风险] 密码更新丢失** → 如果前端在 PUT 请求中遗漏了某个 password 参数（整个条目缺失而非 value="******"），该参数会从 `skill_params` 中消失。Mitigation: 前端应始终回传完整的 `skill_params` 数组，与 `tools` 字段的处理方式一致。

**[风险] `resolve_skill_params` 修改了传入的 param dict** → `decrypt_field` 是 in-place 修改。如果同一个 skill_params 对象被多次使用，第二次调用时已经是明文。Mitigation: 在 `resolve_skill_params` 内对 `skill_params` 做深拷贝后再操作。

**[Trade-off] 简单字符串替换 vs 正则/模板引擎** → 使用 `str.replace("{{key}}", value)` 而非正则或 Jinja2 渲染。简单可控，但不支持默认值、条件等高级语法。当前需求不需要这些，保持简单。

**[风险] 测试执行时前端传入 "******"** → 右侧聊天面板测试时，表单中 password 值为掩码。如果后端直接用前端传来的 `skill_params` 执行替换，`{{password}}` 会被替换为 `"******"` 而非真实密码。Mitigation: 执行路径中，后端应从 DB 的 skill 对象读取 `skill_params`（已加密），而非信任前端传入的值。直接执行接口需要根据 skill ID 从 DB 加载 `skill_params`。
