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
# 危险模式检测（基于已知 SSTI bypass 技术）
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
