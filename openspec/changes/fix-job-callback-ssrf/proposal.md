## Why

安全审计发现 Job NATS API 存在 SSRF 漏洞（BK-LITE-003）：

- **BK-LITE-003 (高危)**: `job_script_execute` 和 `job_file_distribute` 接口接受任意 `callback_url`，任务完成后服务端直接向该 URL 发起 POST 请求，可被利用探测内网或访问云元数据

该漏洞允许能调用 NATS Job API 的主体借 worker 网络位置访问内网资源，必须修复。

## What Changes

- **回调 URL 校验**: 在 NATS API 入口和回调执行前校验 `callback_url`，复用 `fix-opspilot-ssti-ssrf` 中的 `SSRFValidator`
- **回调签名头**: 为回调请求添加签名头，防止被用于伪造内部请求
- **安全日志**: 记录并告警异常 callback 地址

## Capabilities

### New Capabilities

- `callback-url-validation`: 回调 URL 安全校验，阻止私网/云元数据访问
- `callback-request-signing`: 回调请求签名，防止伪造

### Modified Capabilities

- `job-script-execute`: 脚本执行接口增加 callback_url 校验
- `job-file-distribute`: 文件分发接口增加 callback_url 校验
- `job-callback-task`: 回调任务改用安全请求 + 签名头

## Impact

- **server/apps/job_mgmt/nats_api.py**: 入口校验 callback_url
- **server/apps/job_mgmt/services/callback_service.py**: 添加签名头
- **server/apps/job_mgmt/tasks.py**: 使用安全请求
- **server/apps/job_mgmt/utils/callback_signer.py**: 新增签名工具
- **Security**: 关闭 Job 回调 SSRF 攻击向量

## Dependencies

- 依赖 `fix-opspilot-ssti-ssrf` 中创建的 `server/apps/core/utils/ssrf_validator.py`
