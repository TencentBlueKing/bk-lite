# 2026 06 05 Add Skill Prompt Params

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-add-skill-prompt-params/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

LLMSkill 的 `skill_prompt` 中经常需要包含敏感信息（如 browser_use 工具登录网站的账号密码）。当前只能明文写在 prompt 里，存在泄露风险：API 返回、日志、前端展示都会暴露原始凭据。需要一种参数化机制，让用户定义变量并对敏感值加密存储，执行时再替换为真实值。

## What Changes

- LLMSkill 模型新增 `skill_params` JSONField，存储参数列表，每项包含 `key`、`value`、`type`（text/password）
- `type=password` 的参数值使用 `EncryptMixin` 加密存储
- API 读取时，`type=password` 的值返回 `"******"` 掩码，不暴露真实值和密文
- API 更新时，若 `type=password` 且 `value=="******"`，保留 DB 中原有加密值
- 执行时（直接调用 + 工作流 AgentNode），解密参数并将 `skill_prompt` 中的 `{{key}}` 替换为真实值，替换发生在 prompt 进入模板引擎之前
- 意图分类节点（IntentClassifierNode）不受影响——它不使用 LLMSkill，直接选模型和写 prompt

## Capabilities

### New Capabilities
- `skill-prompt-params`: LLMSkill 的 prompt 参数化能力——参数定义、加密存储、掩码读取、执行时替换

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

- **Model**: `server/apps/opspilot/models/model_provider_mgmt.py` — LLMSkill 新增字段 + migration
- **Serializer**: `server/apps/opspilot/serializers/llm_serializer.py` — 读取时掩码 password 值
- **View**: `server/apps/opspilot/viewsets/llm_view.py` — create/update 时加密处理 + "******" 保留逻辑
- **Execution (直接)**: `server/apps/opspilot/services/chat_service.py` — 解密 + `{{key}}` 替换
- **Execution (工作流)**: `server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py` — AgentNode 读取 skill_params 并替换
- **API**: LLMSkill 的 CRUD + execute 接口均受影响
- **DB**: 新增一次 Django migration

## Implementation Decisions

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

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-22
```

## Capability Deltas

### skill-prompt-params

## ADDED Requirements

### Requirement: Skill prompt params field
LLMSkill model SHALL have a `skill_params` JSONField (default: empty list) that stores a list of parameter objects. Each parameter object SHALL contain `key` (string), `value` (string), and `type` (enum: `text` | `password`).

#### Scenario: Create skill with prompt params
- **WHEN** user creates an LLMSkill with `skill_params: [{"key": "username", "value": "admin", "type": "text"}, {"key": "password", "value": "123", "type": "password"}]`
- **THEN** system stores the skill with `type=text` values in plaintext and `type=password` values encrypted via `EncryptMixin`

#### Scenario: Create skill without prompt params
- **WHEN** user creates an LLMSkill without providing `skill_params`
- **THEN** system stores `skill_params` as an empty list `[]`

### Requirement: Password params encrypted at rest
All `skill_params` entries with `type=password` SHALL have their `value` encrypted using `EncryptMixin.encrypt_field()` before persisting to database. Entries with `type=text` SHALL be stored as plaintext.

#### Scenario: Mixed type params storage
- **WHEN** user saves `skill_params: [{"key": "host", "value": "example.com", "type": "text"}, {"key": "token", "value": "secret123", "type": "password"}]`
- **THEN** `host` value is stored as `"example.com"` and `token` value is stored as a Fernet-encrypted string

### Requirement: Password params masked on read
API responses for LLMSkill SHALL return `"******"` as the `value` for all `skill_params` entries with `type=password`. Entries with `type=text` SHALL return their actual value.

#### Scenario: List skills with password params
- **WHEN** client sends GET request to list or retrieve an LLMSkill that has `skill_params` containing a `type=password` entry
- **THEN** response contains `"value": "******"` for that entry, not the encrypted or plaintext value

#### Scenario: List skills with text params
- **WHEN** client sends GET request to list or retrieve an LLMSkill that has `skill_params` containing a `type=text` entry
- **THEN** response contains the actual plaintext value for that entry

### Requirement: Password params preserved on update
When updating LLMSkill, if a `skill_params` entry has `type=password` and `value=="******"`, the system SHALL preserve the existing encrypted value from the database for that key. New password values (not `"******"`) SHALL be encrypted before storage.

#### Scenario: Update without changing password
- **WHEN** client sends PUT with `skill_params` containing `{"key": "password", "value": "******", "type": "password"}`
- **THEN** system keeps the previously stored encrypted value for key `"password"` unchanged

#### Scenario: Update with new password value
- **WHEN** client sends PUT with `skill_params` containing `{"key": "password", "value": "newpass", "type": "password"}`
- **THEN** system encrypts `"newpass"` and stores the new encrypted value

#### Scenario: Update text param normally
- **WHEN** client sends PUT with `skill_params` containing `{"key": "username", "value": "newuser", "type": "text"}`
- **THEN** system stores `"newuser"` as plaintext

### Requirement: Prompt param substitution on execution
When LLMSkill is executed, the system SHALL resolve all `{{key}}` placeholders in `skill_prompt` by replacing them with the actual (decrypted) values from `skill_params`. This substitution SHALL occur before the prompt enters any downstream template engine.

#### Scenario: Direct skill execution with params
- **WHEN** skill executes with `skill_prompt="登陆 xxx，输入帐号 {{username}}，密码 {{password}}"` and `skill_params=[{"key":"username","value":"admin","type":"text"},{"key":"password","value":"<encrypted>","type":"password"}]`
- **THEN** the prompt sent to LLM is `"登陆 xxx，输入帐号 admin，密码 123"` (password decrypted and substituted)

#### Scenario: Execution with no params defined
- **WHEN** skill executes with `skill_params=[]` and `skill_prompt` contains `{{something}}`
- **THEN** the prompt is sent as-is with `{{something}}` unresolved (no error raised)

#### Scenario: Execution with param defined but not referenced in prompt
- **WHEN** skill executes with `skill_params=[{"key":"unused","value":"val","type":"text"}]` and `skill_prompt` does not contain `{{unused}}`
- **THEN** the prompt is sent unchanged (no error raised)

### Requirement: Workflow AgentNode param substitution
When an LLMSkill is invoked through a workflow AgentNode, the system SHALL read the skill's `skill_params` and perform the same `{{key}}` → value substitution on `skill_prompt` before passing it to the chat service.

#### Scenario: AgentNode executes skill with params
- **WHEN** a workflow AgentNode selects an LLMSkill that has `skill_params` with password entries
- **THEN** the `skill_prompt` passed to the chat service has all `{{key}}` placeholders replaced with decrypted values

### Requirement: Intent classifier node unaffected
IntentClassifierNode SHALL NOT be affected by this change. It does not use LLMSkill and constructs its own prompt independently.

#### Scenario: Intent classifier node operates normally
- **WHEN** a workflow uses IntentClassifierNode with a directly configured LLM model and prompt
- **THEN** node behavior is unchanged; no param substitution logic is applied

## Work Checklist

## 1. Model 层

- [x] 1.1 在 `server/apps/opspilot/models/model_provider_mgmt.py` 的 LLMSkill 模型中新增 `skill_params = models.JSONField(default=list, verbose_name="技能参数")`
- [x] 1.2 生成并执行 Django migration：`python manage.py makemigrations opspilot && python manage.py migrate`

## 2. 工具函数

- [x] 2.1 新建 `server/apps/opspilot/utils/prompt_utils.py`，实现 `resolve_skill_params(skill_prompt, skill_params)` 函数：深拷贝 skill_params → 解密 password 类型 → `{{key}}` 替换为真实值 → 返回替换后的 prompt

## 3. Serializer 层

- [x] 3.1 在 `server/apps/opspilot/serializers/llm_serializer.py` 的 LLMSerializer 中新增 `skill_params = serializers.SerializerMethodField()`
- [x] 3.2 实现 `get_skill_params()` 方法：遍历参数列表，`type=password` 的 value 替换为 `"******"` 后返回

## 4. View 层 — 创建

- [x] 4.1 在 `server/apps/opspilot/viewsets/llm_view.py` 的 `create()` 方法中，保存前遍历 `params.get("skill_params", [])`，对 `type=password` 的条目调用 `EncryptMixin.encrypt_field("value", item)`

## 5. View 层 — 更新

- [x] 5.1 在 `llm_view.py` 的 `update()` 方法中，处理 `skill_params` 更新逻辑：遍历新参数列表，`type=password` 且 `value=="******"` 时从 `instance.skill_params` 中找同 key 的旧加密值保留；否则加密新值

## 6. 执行路径 — 直接执行

- [x] 6.1 在 `server/apps/opspilot/services/chat_service.py` 中，构建 `chat_kwargs` 之前（约第 154 行），从 DB 加载 skill 的 `skill_params`（不信任前端传入值），调用 `resolve_skill_params()` 替换 prompt 中的参数
- [x] 6.2 在 `llm_view.py` 的 `execute()` 方法中，根据 skill ID 从 DB 读取 `skill_params` 传入 `chat_service`，确保使用加密存储的真实值而非前端掩码值

## 7. 执行路径 — 工作流 AgentNode

- [x] 7.1 在 `server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py` 的 `_build_llm_params()` 中，读取 `skill.skill_params`，调用 `resolve_skill_params()` 处理 `skill.skill_prompt` 后再赋值到返回字典

## 8. 前端 — Skill 设置页 Prompt 参数区域

- [x] 8.1 在 `web/src/app/opspilot/(pages)/skill/detail/settings/page.tsx` 的 Prompt TextArea 下方，新增 "Prompt 参数" 区域，使用 Ant Design `Form.List name="skill_params"` 渲染动态参数行
- [x] 8.2 每行包含：参数名（Input）、值（根据 type 切换：text→Input，password→EditablePasswordField）、类型（Select: text/password）、删除按钮
- [x] 8.3 添加 "添加参数" 按钮，点击追加空行 `{key: "", value: "", type: "text"}`
- [x] 8.4 保存时将 `skill_params` 数组一并提交到 PUT 请求 payload 中

## 9. 前端 — 测试执行传参

- [x] 9.1 在 `handleSendMessage` 函数中，将当前表单的 `skill_params` 传入执行请求 payload（后端将从 DB 读取真实加密值，前端传入仅用于标识 skill）

## 10. 前端 — 国际化

- [x] 10.1 在 opspilot 的 locale 文件中添加新增 UI 文案的 i18n key（中/英文）："Prompt 参数"、"参数名"、"值"、"类型"、"添加参数" 等

## 11. 前端 — 数据回填

- [x] 11.1 页面加载时，从 GET 接口返回的 `skill_params` 初始化 Form 表单（password 值为 "******"，显示为密码输入框）
- [x] 11.2 编辑保存时，未修改的 password 字段保持 "******" 原样回传，后端保留旧加密值

## 12. 验证

- [x] 12.1 运行 `cd server && make test` 确保后端测试通过
- [x] 12.2 运行 `cd web && pnpm lint && pnpm type-check` 确保前端检查通过
- [x] 12.3 手动验证：创建带 password 参数的 LLMSkill，确认 API 返回掩码值
- [x] 12.4 手动验证：执行带参数的 skill，确认 prompt 中 `{{key}}` 被正确替换
- [x] 12.5 手动验证：在设置页右侧聊天面板测试执行，确认 password 参数能正确替换（非 "******"）
