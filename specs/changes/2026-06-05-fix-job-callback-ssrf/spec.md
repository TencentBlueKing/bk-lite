# 2026 06 05 Fix Job Callback Ssrf

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-fix-job-callback-ssrf/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

安全审计发现 Job NATS API 存在 SSRF 漏洞：

**BK-LITE-003 - Callback SSRF (高危)**:
- 位置: `nats_api.py:294,375`, `tasks.py:215`
- 问题: `callback_url` 从 NATS 请求体直接读取并存储，任务完成后 `do_callback_task` 直接 POST 到该 URL
- PoC: `{"callback_url": "http://169.254.169.254/latest/meta-data/"}`
- 影响: 云元数据泄露、内网探测、可能的内部服务攻击

**当前架构:**
```
┌─────────────────────────────────────────────────────────────────┐
│ Job NATS API                                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  job_script_execute(data)                                       │
│    └─ callback_url = data.get("callback_url")  ← 无校验        │
│    └─ JobExecution.objects.create(callback_url=callback_url)   │
│                                                                 │
│  job_file_distribute(data)                                      │
│    └─ callback_url = data.get("callback_url")  ← 无校验        │
│    └─ JobExecution.objects.create(callback_url=callback_url)   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ Callback Service                                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  send_callback(execution)                                       │
│    └─ callback_url = execution.callback_url    ← 无二次校验    │
│    └─ send_task("do_callback_task", [callback_url, ...])       │
│                                                                 │
│  do_callback_task(url, payload, execution_id)                   │
│    └─ requests.post(url, json=payload)         ← SSRF 漏洞     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Goals / Non-Goals

**Goals:**
- 阻止回调到私网、云元数据、特殊地址
- 为回调请求添加签名，防止伪造
- 记录异常回调地址便于安全监控
- 复用 `fix-opspilot-ssti-ssrf` 中的 SSRF 校验器

**Non-Goals:**
- 实现 callback 注册制白名单（长期方案，需业务改造）
- 修改 NATS API 协议
- 实现回调重试策略调整

## Decisions

### Decision 1: 校验时机 - 入口 + 执行前双重校验

**Choice**: 在 NATS API 入口校验 + 回调执行前二次校验

**Rationale**:
- 入口校验：尽早拒绝非法请求，避免存储脏数据
- 执行前校验：防御数据库被篡改或 DNS rebinding 攻击

### Decision 2: 签名机制

**Choice**: HMAC-SHA256 签名，包含时间戳和 payload

**Rationale**:
- 防止回调被用于伪造内部请求
- 接收方可验证请求来源
- 时间戳防止重放攻击

### Decision 3: 复用 SSRF 校验器

**Choice**: 复用 `fix-opspilot-ssti-ssrf` 中的 `SSRFValidator`

**Rationale**:
- 统一安全策略
- 避免重复代码
- 便于维护和更新黑名单

## Design

### 1. 入口校验 (nats_api.py)

```python
from apps.core.utils.ssrf_validator import SSRFValidator, SSRFError

async def job_script_execute(self, data: dict):
    # 校验 callback_url
    callback_url = data.get("callback_url")
    if callback_url:
        try:
            SSRFValidator.validate_callback(callback_url)
        except SSRFError as e:
            return {"result": False, "message": f"Invalid callback_url: {e}"}

    # ... 继续原有逻辑
```

### 2. 回调签名 (callback_signer.py)

```python
import hmac
import hashlib
import json
import time
from django.conf import settings

def sign_callback(payload: dict, timestamp: int) -> str:
    """生成 HMAC-SHA256 签名"""
    secret = getattr(settings, 'CALLBACK_SECRET_KEY', settings.SECRET_KEY)
    payload_str = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    message = f"{timestamp}:{payload_str}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

def get_signed_headers(payload: dict) -> dict:
    """获取带签名的请求头"""
    timestamp = int(time.time())
    return {
        'X-BK-Lite-Timestamp': str(timestamp),
        'X-BK-Lite-Signature': sign_callback(payload, timestamp),
        'X-BK-Lite-Source': 'job-callback',
        'Content-Type': 'application/json',
    }
```

### 3. 安全回调执行 (tasks.py)

```python
from apps.core.utils.ssrf_validator import SSRFValidator, SSRFError
from apps.core.utils.safe_requests import safe_post
from apps.job_mgmt.utils.callback_signer import get_signed_headers

@shared_task(bind=True, max_retries=5, ...)
def do_callback_task(self, url: str, payload: dict, execution_id: int) -> None:
    # 二次校验（防御 DNS rebinding）
    try:
        SSRFValidator.validate_callback(url)
    except SSRFError as e:
        logger.error(f"[callback] SSRF 阻断: execution_id={execution_id}, url={url}, error={e}")
        return  # 不重试

    # 添加签名头
    headers = get_signed_headers(payload)

    # 安全请求
    resp = safe_post(url, json=payload, headers=headers, timeout=10)
    # ... 原有响应处理逻辑
```

### 4. 改造后架构

```
┌─────────────────────────────────────────────────────────────────┐
│ Job NATS API (修复后)                                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  job_script_execute(data)                                       │
│    └─ SSRFValidator.validate_callback(callback_url) ← 入口校验 │
│    └─ JobExecution.objects.create(callback_url=callback_url)   │
│                                                                 │
│  job_file_distribute(data)                                      │
│    └─ SSRFValidator.validate_callback(callback_url) ← 入口校验 │
│    └─ JobExecution.objects.create(callback_url=callback_url)   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ Callback Service (修复后)                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  send_callback(execution)                                       │
│    └─ callback_url = execution.callback_url                    │
│    └─ send_task("do_callback_task", [callback_url, ...])       │
│                                                                 │
│  do_callback_task(url, payload, execution_id)                   │
│    └─ SSRFValidator.validate_callback(url)      ← 二次校验     │
│    └─ headers = get_signed_headers(payload)     ← 签名头       │
│    └─ safe_post(url, json=payload, headers=headers) ← 安全请求 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Risks

- **兼容性**: 现有使用私网 callback_url 的调用方会失败，需要提前通知
- **签名验证**: 接收方需要实现签名验证才能获得防伪造保护（可选）

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-28
```

## Work Checklist

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
