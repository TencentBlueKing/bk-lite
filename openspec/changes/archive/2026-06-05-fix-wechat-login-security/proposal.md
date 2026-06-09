# Proposal: 修复微信登录安全漏洞

## Why

### 问题背景
GitHub Issue #2899 报告了一个严重的安全漏洞：

**`/api/wechat_user_register/` 接口可被攻击者直接调用，传入任意 `user_id` 即可获得该账号的登录态，导致任意账号接管。**

### 漏洞原因

当前架构中，微信 OAuth 验证在 Next.js 前端完成，但后端接口是公开的：

```
正常流程：用户 → 微信授权 → Next.js 验证 code → 获取 openid → 调用后端 → 签发 token
攻击流程：攻击者 → 直接调用后端 /api/wechat_user_register/ → 签发 token（绕过验证）
```

### 影响范围
- 任意已存在账号可被接管
- 攻击者可创建新账号并获得 guest 权限
- 如果目标是管理员账号，攻击者获得全站最高权限

## What Changes

### 方案：将微信 OAuth 验证移到后端

1. **新增后端接口** `POST /api/wechat_login/`
   - 接收微信授权 code
   - 后端调用微信 API 验证 code，获取 openid
   - 用 openid 创建/获取本地用户
   - 签发 JWT token

2. **简化前端逻辑**
   - 前端只负责获取微信 code
   - 直接将 code 传给后端新接口
   - 不再直接调用微信 API

3. **废弃旧接口**
   - 移除 `/api/wechat_user_register/` 接口

4. **开发调试支持**
   - 添加 Mock 模式，本地开发时可跳过真实微信验证
   - Mock 返回与真实 API 相同的数据结构，确保行为一致

### 安全保障
- 微信 code 只能使用一次，且必须配合 app_secret 才能换取 openid
- Mock 模式仅在 `DEBUG=True` 时生效，生产环境永不执行
- 上线前必须在测试环境用真实微信扫码验证

## References

- GitHub Issue: https://github.com/TencentBlueKing/bk-lite/issues/2899
- 微信 OAuth 文档: https://developers.weixin.qq.com/doc/oplatform/Website_App/WeChat_Login/Wechat_Login.html
