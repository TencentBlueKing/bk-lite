## 1. 回调签名工具 (server/apps/job_mgmt/utils/)

- [x] 1.1 创建 `callback_signer.py` 文件
- [x] 1.2 实现 `sign_callback(payload, timestamp)` 函数，使用 HMAC-SHA256 生成签名
- [x] 1.3 实现 `get_signed_headers(payload)` 函数，返回包含时间戳、签名、来源的请求头字典

## 2. NATS API 入口校验 (server/apps/job_mgmt/nats_api.py)

- [x] 2.1 导入 `SSRFValidator` 和 `SSRFError` from `apps.core.utils.ssrf_validator`
- [x] 2.2 在 `job_script_execute()` 方法中添加 callback_url 校验（约 line 294）
- [x] 2.3 在 `job_file_distribute()` 方法中添加 callback_url 校验（约 line 375）
- [x] 2.4 校验失败时返回 `{"result": False, "message": "Invalid callback_url: {error}"}`

## 3. 回调任务安全改造 (server/apps/job_mgmt/tasks.py)

- [x] 3.1 导入 `SSRFValidator`, `SSRFError` from `apps.core.utils.ssrf_validator`
- [x] 3.2 导入 `safe_post` from `apps.core.utils.safe_requests`
- [x] 3.3 导入 `get_signed_headers` from `apps.job_mgmt.utils.callback_signer`
- [x] 3.4 在 `do_callback_task()` 开头添加二次 SSRF 校验
- [x] 3.5 SSRF 校验失败时记录错误日志并直接返回（不重试）
- [x] 3.6 调用 `get_signed_headers(payload)` 获取签名头
- [x] 3.7 将 `requests.post(url, json=payload, timeout=10)` 替换为 `safe_post(url, json=payload, headers=headers, timeout=10)`

## 4. 测试用例

- [x] 4.1 在 `server/apps/job_mgmt/tests/test_callback_service.py` 中添加 SSRF 阻断测试
- [x] 4.2 测试私网地址被拒绝：`http://192.168.1.1/callback`
- [x] 4.3 测试云元数据地址被拒绝：`http://169.254.169.254/latest/meta-data/`
- [x] 4.4 测试公网地址通过：`https://example.com/callback`
- [x] 4.5 测试签名头生成正确性

## 5. 验证

- [x] 5.1 运行 `cd server && make test` 验证所有测试通过（144 tests passed）
- [x] 5.2 手动验证 SSRF PoC 被阻断：通过 NATS 发送 `{"callback_url": "http://169.254.169.254/"}`（通过单元测试验证）
- [x] 5.3 验证正常公网回调功能不受影响（通过单元测试验证）
- [x] 5.4 验证回调请求包含签名头 `X-BK-Lite-Signature`（通过单元测试验证）
