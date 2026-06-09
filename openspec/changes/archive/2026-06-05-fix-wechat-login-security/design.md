# Design: 微信登录安全修复

## 架构变更

### 当前架构（不安全）

```
用户 → 微信授权 → Next.js 前端 → 调用微信 API 获取 openid
                       │
                       ▼
              POST /api/wechat_user_register/
              { user_id: openid }
                       │
                       ▼
              Django 后端（无验证，直接签发 token）
```

**漏洞**：攻击者可直接调用后端接口，绕过前端的微信验证。

### 目标架构（安全）

```
用户 → 微信授权 → Next.js 前端 → POST /api/wechat_login/
                                 { code: "微信授权码" }
                                        │
                                        ▼
                               Django 后端
                                        │
                                        ▼
                               调用微信 API 验证 code
                               获取 openid
                                        │
                                        ▼
                               用 openid 创建/获取用户
                               签发 JWT token
```

**安全**：code 只能使用一次，且必须配合 app_secret 才能换取 openid。

## 后端设计

### 新增接口：`POST /api/wechat_login/`

**Request:**
```json
{
    "code": "微信授权码"
}
```

**Response (成功):**
```json
{
    "result": true,
    "data": {
        "id": 123,
        "username": "oXk8s5xxxxxxxxxxxxxxxxxxx",
        "display_name": "微信昵称",
        "token": "jwt...",
        "is_first_login": true,
        "locale": "zh",
        "timezone": "Asia/Shanghai"
    }
}
```

**Response (失败):**
```json
{
    "result": false,
    "message": "Invalid WeChat code"
}
```

### 核心函数：`verify_wechat_code()`

统一入口，Mock 和真实 API 返回相同结构：

```python
def verify_wechat_code(code: str) -> dict:
    """
    Returns:
        {
            "success": bool,
            "openid": str,       # 成功时
            "nickname": str,     # 成功时
            "unionid": str,      # 成功时（可选）
            "error": str,        # 失败时
            "errcode": int       # 失败时（可选）
        }
    """
```

### Mock 模式设计

**触发条件**：`DEBUG=True` 且 `WECHAT_MOCK_MODE=True`

**Mock 数据格式**：与真实微信 API 返回格式一致
- openid: 28位，以 `o` 开头
- nickname: 支持 emoji
- 支持模拟错误场景（code=invalid, code=expired, code=timeout）

**安全保障**：
- 双重条件检查，生产环境 `DEBUG=False` 时永不执行
- Mock 模式打 warning 日志，便于发现误配置

## 前端设计

### 修改 `web/src/app/api/wechat-popup-login/route.ts`

**Before:**
```typescript
// 1. 获取微信配置
// 2. 用 code 换 access_token（调用微信 API）
// 3. 用 access_token 获取用户信息（调用微信 API）
// 4. 调用后端 /api/wechat_user_register/
```

**After:**
```typescript
// 1. 直接将 code 传给后端
const response = await fetch(`${NEXTAPI_URL}/api/v1/core/api/wechat_login/`, {
    method: 'POST',
    body: JSON.stringify({ code }),
});
// 2. 返回后端响应
```

### 修改 `web/src/lib/wechatProvider.ts`

调整 `authorize` 回调逻辑，使用新的后端接口。

## 废弃接口

| 接口 | 处理方式 |
|------|----------|
| `POST /api/wechat_user_register/` | 移除路由和视图函数 |

## 测试策略

| 层级 | 测试内容 | 方法 |
|------|----------|------|
| 单元测试 | `verify_wechat_code()` 函数 | Mock 微信 API 响应 |
| 单元测试 | Mock 模式返回结构 | 验证与真实 API 一致 |
| 单元测试 | 错误处理 | 覆盖所有错误码 |
| 集成测试 | 完整登录流程 | Mock 模式 |
| E2E 测试 | 真实微信扫码 | 测试环境手动验证 |

## 上线验证清单

- [ ] Mock 返回结构与真实 API 一致
- [ ] openid 格式正确（28位，以 `o` 开头）
- [ ] nickname 支持 emoji（数据库能存储）
- [ ] 错误处理完整（覆盖所有错误码）
- [ ] 超时处理正确（10秒超时返回错误）
- [ ] **测试环境真实微信扫码验证通过**
