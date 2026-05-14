## Context

### 当前架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           当前登录流程                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   前端                        后端                                           │
│   ┌──────┐                   ┌──────────────────────────────────┐          │
│   │ 登录 │ ─── POST /login ──▶│ nats_api.login()                │          │
│   │ 页面 │                    │   ├─ 验证用户名+密码             │          │
│   └──────┘                    │   └─ get_user_login_token()     │          │
│      │                        │       ├─ 签发 JWT ⚠️             │          │
│      │                        │       └─ 返回 token + enable_otp│          │
│      │                        └──────────────────────────────────┘          │
│      │                                       │                              │
│      │◀──────────────────────────────────────┘                              │
│      │  { token: "xxx", enable_otp: true }                                  │
│      │                                                                      │
│      ▼                                                                      │
│   ┌──────────────────────────────────────────────────────────────────┐     │
│   │ index_view.login() 设置 bklite_token Cookie ⚠️                    │     │
│   │ 前端判断 enable_otp → 显示 OTP 页面（但 token 已有效）             │     │
│   └──────────────────────────────────────────────────────────────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 涉及组件

| 组件 | 文件 | 职责 |
|------|------|------|
| NATS API | `server/apps/system_mgmt/nats_api.py` | 用户认证逻辑、OTP 管理 |
| Core Views | `server/apps/core/views/index_view.py` | HTTP 接口、Cookie 管理 |
| Auth Middleware | `server/apps/core/middlewares/auth_middleware.py` | 请求认证拦截 |
| URLs | `server/apps/core/urls.py` | 路由配置 |

### 约束

- 必须保持向后兼容：未启用 OTP 的用户登录流程不变
- 不能引入新的外部依赖
- challenge_id 存储需要考虑分布式部署场景（多实例）

## Goals / Non-Goals

**Goals:**
- 修复 Issue #2846：确保 OTP 验证在后端强制执行，两个因子都通过才签发 token
- 修复 Issue #2951：OTP 管理接口需要权限保护，不能任意操作他人账户
- 保持未启用 OTP 用户的登录体验不变
- 提供合理的安全措施（频率限制、有效期）

**Non-Goals:**
- 不重构整个认证系统，只修复 OTP 相关漏洞
- 不引入新的 2FA 方式（如 SMS、Email）
- 不修改 JWT 的签发逻辑和格式
- 不处理 OTP 恢复码（recovery codes）功能

## Decisions

### Decision 1: Challenge 存储方案

**选择：使用 Django Cache（Redis）存储 challenge**

| 方案 | 优点 | 缺点 |
|------|------|------|
| **Django Cache (Redis)** ✅ | 分布式支持、自动过期、已有基础设施 | 需要 Redis 可用 |
| 数据库表 | 持久化、可审计 | 需要清理机制、增加 DB 负载 |
| 内存字典 | 简单 | 不支持多实例、重启丢失 |
| JWT 临时 token | 无状态 | 无法撤销、复杂度高 |

**实现**：
```python
# 存储 challenge
cache_key = f"otp_challenge:{challenge_id}"
cache.set(cache_key, {
    "user_id": user.id,
    "username": username,
    "created_at": now.isoformat(),
}, timeout=300)  # 5 分钟过期
```

### Decision 2: 登录 API 响应结构

**选择：条件返回，启用 OTP 时返回 challenge_id 而非 token**

```python
# 未启用 OTP（行为不变）
{
    "result": True,
    "data": {
        "token": "jwt_xxx",
        "username": "user1",
        # ... 其他字段
    }
}

# 启用 OTP（新行为）
{
    "result": True,
    "data": {
        "require_otp": True,           # 新字段，标识需要 OTP 验证
        "challenge_id": "uuid_xxx",    # 临时凭证
        "username": "user1",
        # 不返回 token
    }
}
```

**理由**：最小化 API 变更，前端通过 `require_otp` 字段判断流程分支。

### Decision 3: OTP 验证接口设计

**选择：新增独立的登录 OTP 验证接口**

```
POST /api/verify_otp_login/
{
    "challenge_id": "uuid_xxx",
    "otp_code": "123456"
}
```

**理由**：
- 与现有 `verify_otp_code`（用于 OTP 绑定验证）职责分离
- 登录场景的 OTP 验证需要 challenge_id，绑定场景需要登录态
- 避免混淆两种不同的验证场景

### Decision 4: OTP 管理接口权限模型

**选择：移除 @api_exempt，绑定当前登录用户**

| 接口 | 当前 | 修复后 |
|------|------|--------|
| `generate_qr_code` | `@api_exempt`，接受 username 参数 | 需要登录态，只能为 `request.user` 生成 |
| `verify_otp_code` | `@api_exempt`，接受 username 参数 | 需要登录态，只能验证 `request.user` |

**特殊情况**：首次绑定 OTP 时用户尚未完成 OTP 验证，如何访问这些接口？

**解决方案**：引入"待 OTP 绑定"的中间状态
- 用户首次启用 OTP 时，密码验证通过后返回一个特殊的 `setup_token`
- `setup_token` 只允许访问 OTP 绑定相关接口，不能访问其他 API
- 绑定完成后，`setup_token` 失效，用户需要用新绑定的 OTP 完成登录

### Decision 5: 频率限制策略

**选择：基于 IP + 用户名的组合限制**

```python
# OTP 验证失败限制
MAX_OTP_ATTEMPTS = 5
LOCKOUT_DURATION = 300  # 5 分钟

# 限制键
rate_limit_key = f"otp_attempts:{ip}:{username}"
```

**理由**：
- 仅限制 IP 可能误伤 NAT 后的合法用户
- 仅限制用户名可能被用于 DoS 攻击（锁定他人账户）
- 组合限制平衡安全性和可用性

## Risks / Trade-offs

### Risk 1: 前端适配工作量
**风险**：登录流程变更需要前端配合修改
**缓解**：
- 提供详细的 API 变更文档
- 前端可通过 `require_otp` 字段判断新旧流程
- 未启用 OTP 的用户完全不受影响

### Risk 2: Challenge 存储依赖 Redis
**风险**：Redis 不可用时 OTP 登录失败
**缓解**：
- Redis 已是系统核心依赖（Celery、缓存）
- 可配置降级策略：Redis 不可用时临时禁用 OTP 强制验证（需管理员确认）

### Risk 3: 现有集成中断
**风险**：依赖直接获取 token 的第三方集成会失败
**缓解**：
- 文档明确标注 BREAKING CHANGE
- 提供迁移指南
- 考虑提供 API 版本或配置开关（不推荐长期保留）

### Risk 4: OTP 绑定流程复杂化
**风险**：首次绑定 OTP 的用户体验变复杂
**缓解**：
- `setup_token` 机制确保流程可行
- 前端引导用户完成绑定流程
- 绑定完成后立即生效，无需重新登录

## Migration Plan

### 阶段 1: 后端实现（本次变更）
1. 实现 challenge 存储机制
2. 修改 `login()` 返回逻辑
3. 新增 `verify_otp_login()` 接口
4. 收紧 OTP 管理接口权限
5. 添加频率限制

### 阶段 2: 前端适配
1. 登录页面适配两阶段流程
2. OTP 绑定页面适配新接口
3. 错误处理和用户提示

### 回滚策略
- 代码回滚：`git revert` 相关提交
- 数据回滚：无数据库 schema 变更，无需数据回滚
- 配置回滚：如有配置开关，可临时禁用新流程

## Open Questions

1. **setup_token 是否需要？** 
   - 如果用户必须先完成 OTP 绑定才能启用 OTP，则不需要
   - 如果允许管理员为用户强制启用 OTP，则需要 setup_token 机制
   - **建议**：先实现简单方案（用户自行绑定后启用），后续按需扩展

2. **是否需要 OTP 恢复码？**
   - 用户丢失 OTP 设备时如何恢复？
   - **建议**：本次不实现，作为后续增强功能
