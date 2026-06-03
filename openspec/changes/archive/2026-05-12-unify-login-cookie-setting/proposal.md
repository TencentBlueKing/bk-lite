# Proposal: 统一登录入口的 Cookie 设置

## 问题

当前系统有多个登录入口，但只有 `login()` 视图正确设置了 `bklite_token` cookie：

| 入口 | 文件位置 | 设置 Cookie? | 返回 Token? |
|------|----------|--------------|-------------|
| `login()` | index_view.py:89-156 | ✅ | ✅ |
| `wechat_user_register()` | index_view.py:201-255 | ❌ **缺失** | ✅ |

这导致微信登录用户虽然获得了 token，但浏览器没有存储 cookie，后续请求无法自动携带认证信息。

## 目标

1. 确保所有登录入口在成功时都设置相同的 `bklite_token` cookie
2. 提取公共的 cookie 设置逻辑，避免代码重复
3. 保持 cookie 参数的一致性（max_age, path, secure, httponly, samesite）

## 方案

### 提取公共辅助函数

在 `index_view.py` 中创建 `_set_auth_cookie_on_response()` 辅助函数：

```python
def _set_auth_cookie_on_response(response, token):
    """
    统一设置认证 cookie。
    
    在所有登录入口成功后调用此函数，确保 cookie 设置的一致性。
    """
    login_expired_time = 3600 * 24  # default 24h
    try:
        setting = SystemSettings.objects.filter(key="login_expired_time").first()
        if setting:
            login_expired_time = int(float(setting.value) * 3600)
    except Exception:
        pass
    
    response.set_cookie(
        "bklite_token",
        token,
        max_age=login_expired_time,
        path="/",
        secure=not django_settings.DEBUG,
        httponly=True,
        samesite="Lax",
    )
```

### 修改点

1. **`login()` 视图** - 将现有的 cookie 设置代码替换为调用辅助函数
2. **`wechat_user_register()` 视图** - 新增 cookie 设置逻辑

## 影响范围

- 文件：`server/apps/core/views/index_view.py`
- 无数据库变更
- 无 API 接口变更（响应体不变，只是增加了 Set-Cookie header）

## 验证

1. 微信登录后检查浏览器是否存储了 `bklite_token` cookie
2. 普通登录功能不受影响
3. Cookie 参数（httponly, secure, samesite）与原有行为一致
