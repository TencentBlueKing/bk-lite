# 2026 05 29 Fix Opspilot Ssti Ssrf

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-29-fix-opspilot-ssti-ssrf/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

安全审计发现 OpsPilot 模块存在两个高危漏洞（BK-LITE-001、BK-LITE-002）：

1. **BK-LITE-001 (严重)**: ChatFlow 工作流使用默认 `jinja2.Template` 渲染用户可控模板，攻击者可通过 SSTI payload 在服务端执行任意命令
2. **BK-LITE-002 (高危)**: HTTP Action 节点和 Fetch 工具未校验目标 URL，可被利用进行 SSRF 攻击，访问云元数据或内网服务

这两个漏洞允许具有工作流编辑权限的用户获取服务器控制权或探测内网，必须立即修复。

## What Changes

- **安全模板渲染**: 新增 `safe_template.py` 工具，使用白名单变量替换 + 危险模式检测替代默认 Jinja2 Template
- **SSRF URL 校验**: 新增 `ssrf_validator.py` 工具，实现完整的 IP 黑名单校验（含云元数据、私网、特殊地址）
- **安全 HTTP 请求**: 新增 `safe_requests.py` 封装，自动进行 SSRF 校验和重定向目标验证

## Capabilities

### New Capabilities

- `safe-template-rendering`: 安全的模板变量替换，阻止 SSTI 攻击
- `ssrf-url-validation`: 统一的 SSRF URL 校验器，阻止私网/云元数据访问
- `safe-http-requests`: 安全的 HTTP 请求封装，自动校验 URL 和重定向

### Modified Capabilities

- `chatflow-template-rendering`: 工作流节点模板渲染改用安全实现
- `http-action-node`: HTTP 动作节点改用安全请求
- `fetch-tool`: Fetch 工具改用安全请求

## Impact

- **server/apps/core/utils/**: 新增 3 个安全工具模块
- **server/apps/opspilot/utils/chat_flow_utils/nodes/**: 4 个节点文件改用安全模板渲染
- **server/apps/opspilot/metis/llm/tools/fetch/**: Fetch 工具改用安全请求
- **Security**: 关闭 SSTI 和 SSRF 攻击向量

## Implementation Decisions

## Context

安全审计发现 OpsPilot ChatFlow 存在两个严重漏洞：

**BK-LITE-001 - Jinja2 SSTI (严重)**:
- 位置: `nodes/action/action.py:33`, `nodes/agent/agent.py:87`, `nodes/intent/intent_classifier.py:62`
- 问题: 使用默认 `jinja2.Template` 渲染用户可控模板
- PoC: `{{ cycler.__init__.__globals__.os.popen('id').read() }}`
- 影响: 服务端任意命令执行

**BK-LITE-002 - SSRF (高危)**:
- 位置: `nodes/action/action.py:117-141`, `metis/llm/tools/fetch/utils.py:42-69`
- 问题: HTTP 请求未校验目标 URL，`validate_url` 仅检查格式
- PoC: `http://169.254.169.254/latest/meta-data/`
- 影响: 云元数据泄露、内网探测

**当前架构:**
```
┌─────────────────────────────────────────────────────────────────┐
│ ChatFlow Engine                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  HttpActionNode._render_template()                              │
│    └─ jinja2.Template(content).render()  ← SSTI 漏洞           │
│    └─ requests.get/post(url)             ← SSRF 漏洞           │
│                                                                 │
│  AgentNode._render_prompt()                                     │
│    └─ jinja2.Template(prompt).render()   ← SSTI 漏洞           │
│                                                                 │
│  NotifyNode._render_content()                                   │
│    └─ jinja2.Template(content).render()  ← SSTI 漏洞           │
│                                                                 │
│  IntentClassifier._render_prompt()                              │
│    └─ jinja2.Template(prompt).render()   ← SSTI 漏洞           │
│                                                                 │
│  Fetch Tool (http.py)                                           │
│    └─ validate_url() 仅检查格式          ← SSRF 漏洞           │
│    └─ requests.get/post(url)             ← SSRF 漏洞           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Goals / Non-Goals

**Goals:**
- 阻止所有已知 SSTI payload 执行
- 阻止访问私网、云元数据、特殊地址
- 提供可复用的安全工具供其他模块使用
- 保持工作流模板变量功能正常工作

**Non-Goals:**
- 重新设计工作流引擎架构
- 实现完整的 WAF 功能
- 修改前端工作流编辑器

## Decisions

### Decision 1: SSTI 修复策略 - 白名单变量替换

**Choice**: 使用白名单正则匹配 + 危险模式检测，仅允许简单变量插值

**Alternatives Considered**:
- A) `SandboxedEnvironment` → 仍有绕过风险（cycler/joiner/namespace 等对象可访问 `__globals__`）
- B) 完全禁用模板功能 → 破坏现有工作流功能
- C) **白名单变量替换** → 最安全，仅允许 `{{ var }}` 和 `{{ var.prop }}` 模式

**Rationale**: 工作流场景只需简单变量插值（如 `{{ last_message }}`、`{{ memory_context }}`），不需要过滤器、控制语句等高级功能。白名单方案彻底消除 SSTI 攻击面。

### Decision 2: SSRF 修复策略 - DNS 解析后校验

**Choice**: 解析 DNS 后校验所有 IP，阻断私网/云元数据/特殊地址

**Alternatives Considered**:
- A) 仅校验主机名 → 无法防御 DNS rebinding
- B) 业务白名单 → 需要配置管理，不适合通用工具
- C) **DNS 解析后校验** → 防御 DNS rebinding，完整 IP 黑名单

**Rationale**: 基于 OWASP SSRF Prevention Cheat Sheet 和 Drawbridge 库最佳实践，DNS 解析后校验是防御 SSRF 的标准做法。

### Decision 3: 安全工具放置位置

**Choice**: 放在 `server/apps/core/utils/` 供全局复用

**Rationale**: SSRF 校验器和安全请求封装可被多个模块复用（OpsPilot、Job、Webhook 等），放在 core 模块便于统一维护。

## Design

### 1. 安全模板渲染 (safe_template.py)

```python
DANGEROUS_PATTERNS = [
    (r'__\w+__', 'dunder 属性访问'),
    (r'\bcycler\b', 'cycler 对象'),
    (r'\bjoiner\b', 'joiner 对象'),
    (r'\{%', 'Jinja2 控制语句'),
    (r'\|', 'Jinja2 过滤器'),
    (r'\[', '下标访问'),
    (r'\(', '函数调用'),
    # ... 完整列表见实现
]

# 白名单变量模式
SAFE_VAR_PATTERN = re.compile(r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\s*\}\}')

def safe_render(template_str: str, context: dict) -> str:
    """安全的模板变量替换"""
    check_dangerous_patterns(template_str)  # 抛出 TemplateSecurityError
    return SAFE_VAR_PATTERN.sub(replace_var, template_str)
```

### 2. SSRF URL 校验器 (ssrf_validator.py)

```python
# 完整 IP 黑名单（基于 OWASP + RFC）
BLOCKED_NETWORKS = [
    # IPv4
    ipaddress.ip_network('127.0.0.0/8'),       # Loopback
    ipaddress.ip_network('10.0.0.0/8'),        # Private A
    ipaddress.ip_network('172.16.0.0/12'),     # Private B
    ipaddress.ip_network('192.168.0.0/16'),    # Private C
    ipaddress.ip_network('169.254.0.0/16'),    # Link-local + Cloud Metadata
    # ... 完整列表见实现

    # IPv6
    ipaddress.ip_network('::1/128'),           # Loopback
    ipaddress.ip_network('fc00::/7'),          # Unique-local
    ipaddress.ip_network('fe80::/10'),         # Link-local
    # ... 完整列表见实现
]

class SSRFValidator:
    @classmethod
    def validate(cls, url: str, allowlist: set[str] | None = None) -> str:
        """校验 URL 安全性"""
        # 1. 协议校验 (仅 http/https)
        # 2. 云元数据主机名直接阻断
        # 3. DNS 解析后校验所有 IP
        # 4. 可选白名单模式
```

### 3. 安全 HTTP 请求 (safe_requests.py)

```python
def safe_request(method: str, url: str, *, allow_redirects: bool = False, **kwargs) -> Response:
    """安全的 HTTP 请求"""
    # 1. 校验原始 URL
    validated_url = SSRFValidator.validate(url)

    # 2. 禁用自动重定向，手动处理
    kwargs['allow_redirects'] = False
    response = requests.request(method, validated_url, **kwargs)

    # 3. 手动校验重定向目标
    while response.is_redirect and allow_redirects:
        redirect_url = response.headers.get('Location')
        SSRFValidator.validate(redirect_url)  # 校验重定向目标
        response = requests.request(method, redirect_url, **kwargs)

    return response
```

### 4. 改造后架构

```
┌─────────────────────────────────────────────────────────────────┐
│ ChatFlow Engine (修复后)                                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  HttpActionNode._render_template()                              │
│    └─ safe_render(content, context)      ← 安全模板渲染        │
│    └─ safe_request(method, url)          ← 安全 HTTP 请求      │
│                                                                 │
│  AgentNode._render_prompt()                                     │
│    └─ safe_render(prompt, context)       ← 安全模板渲染        │
│                                                                 │
│  NotifyNode._render_content()                                   │
│    └─ safe_render(content, context)      ← 安全模板渲染        │
│                                                                 │
│  IntentClassifier._render_prompt()                              │
│    └─ safe_render(prompt, context)       ← 安全模板渲染        │
│                                                                 │
│  Fetch Tool (http.py)                                           │
│    └─ SSRFValidator.validate(url)        ← SSRF 校验           │
│    └─ safe_request(method, url)          ← 安全 HTTP 请求      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Risks

- **功能影响**: 使用高级模板语法的现有工作流可能失效，需要迁移到简单变量语法
- **性能影响**: DNS 解析增加少量延迟（可忽略）
- **误报风险**: 危险模式检测可能误报合法内容（如变量名包含 `config`），需要根据实际情况调整

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-28
```

## Work Checklist

## 1. 安全工具模块 (server/apps/core/utils/)

- [x] 1.1 创建 `safe_template.py`，实现 `TemplateSecurityError` 异常类
- [x] 1.2 实现 `DANGEROUS_PATTERNS` 危险模式列表（覆盖 dunder、cycler/joiner/namespace、控制语句、过滤器、函数调用等）
- [x] 1.3 实现 `check_dangerous_patterns()` 函数，检测并抛出 `TemplateSecurityError`
- [x] 1.4 实现 `SAFE_VAR_PATTERN` 白名单正则，仅匹配 `{{ var }}` 和 `{{ var.prop }}` 模式
- [x] 1.5 实现 `safe_render()` 函数，先检测危险模式，再进行白名单变量替换
- [x] 1.6 创建 `ssrf_validator.py`，实现 `SSRFError` 异常类
- [x] 1.7 实现 `BLOCKED_NETWORKS` 完整 IP 黑名单（IPv4 + IPv6，含云元数据、私网、特殊地址）
- [x] 1.8 实现 `CLOUD_METADATA_HOSTS` 云元数据主机名集合
- [x] 1.9 实现 `SSRFValidator.validate()` 方法，包含协议校验、DNS 解析、IP 黑名单检查
- [x] 1.10 实现 `SSRFValidator.validate_callback()` 方法，供 Job 模块复用
- [x] 1.11 创建 `safe_requests.py`，实现 `SafeRequestsError` 异常类
- [x] 1.12 实现 `safe_request()` 函数，自动 SSRF 校验 + 重定向目标校验
- [x] 1.13 实现便捷方法 `safe_get/safe_post/safe_put/safe_delete/safe_patch`

## 2. SSTI 修复 (server/apps/opspilot/utils/chat_flow_utils/nodes/)

- [x] 2.1 修改 `action/action.py`，导入 `safe_render`，替换 `HttpActionNode._render_template()` 中的 `jinja2.Template().render()`
- [x] 2.2 修改 `action/action.py`，替换 `NotifyNode._render_content()` 中的 `jinja2.Template().render()`
- [x] 2.3 修改 `agent/agent.py`，导入 `safe_render`，替换 `AgentNode._render_prompt()` 中的 `jinja2.Template().render()`
- [x] 2.4 修改 `intent/intent_classifier.py`，导入 `safe_render`，替换 `IntentClassifier._render_prompt()` 中的 `jinja2.Template().render()`
- [x] 2.5 移除上述文件中不再需要的 `import jinja2` 语句

## 3. SSRF 修复 - HTTP Action 节点

- [x] 3.1 修改 `action/action.py`，导入 `safe_get/safe_post/safe_put/safe_patch/safe_delete`
- [x] 3.2 替换 `HttpActionNode._send_http_request()` 中的 `requests.get/post/put/patch/delete` 为安全版本
- [x] 3.3 移除不再需要的 `import requests` 语句（如果完全不再使用）

## 4. SSRF 修复 - Fetch 工具 (server/apps/opspilot/metis/llm/tools/fetch/)

- [x] 4.1 修改 `utils.py`，重写 `validate_url()` 函数，调用 `SSRFValidator.validate()`
- [x] 4.2 修改 `http.py`，导入 `safe_request` 或直接使用 `SSRFValidator.validate()` + 原有 requests（验证：所有5个_http_*_impl函数已调用validate_url()，无需额外修改）
- [x] 4.3 确保 `fetch_get/fetch_post/fetch_put/fetch_delete/fetch_patch` 都经过 SSRF 校验（验证：通过validate_url()统一入口实现）

## 5. 测试用例

- [x] 5.1 创建 `server/apps/core/tests/test_safe_template.py`，测试简单变量替换
- [x] 5.2 添加 SSTI payload 测试用例（cycler、__class__、__globals__、控制语句、过滤器等）
- [x] 5.3 创建 `server/apps/core/tests/test_ssrf_validator.py`，测试公网 URL 通过
- [x] 5.4 添加私网/云元数据/特殊地址阻断测试用例
- [x] 5.5 添加非法协议（ftp/file/gopher）阻断测试用例
- [x] 5.6 添加白名单模式测试用例

## 6. 验证

- [x] 6.1 运行 `cd server && make test` 验证所有测试通过（79 tests passed）
- [x] 6.2 手动验证 SSTI PoC 被阻断：`{{ cycler.__init__.__globals__.os.popen('id').read() }}`（通过单元测试验证）
- [x] 6.3 手动验证 SSRF PoC 被阻断：`http://169.254.169.254/latest/meta-data/`（通过单元测试验证）
- [x] 6.4 验证正常工作流模板功能不受影响：`{{ last_message }}`、`{{ memory_context }}`（通过单元测试验证）
