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
