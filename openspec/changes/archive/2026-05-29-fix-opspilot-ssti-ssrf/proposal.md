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
