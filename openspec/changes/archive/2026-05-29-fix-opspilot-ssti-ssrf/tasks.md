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
