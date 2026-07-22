# Proposal: 统一登录入口的 Cookie 设置

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-12-unify-login-cookie-setting/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-12
```

## Work Checklist

## 任务列表

- [x] **Task 1**: 在 `index_view.py` 中添加 `_set_auth_cookie_on_response()` 辅助函数
  - 位置：在现有辅助函数（如 `_get_loader`）附近
  - 从 `login()` 视图中提取 cookie 设置逻辑
  - 包含 `login_expired_time` 的读取逻辑

- [x] **Task 2**: 重构 `login()` 视图使用新的辅助函数
  - 替换 L136-154 的 cookie 设置代码
  - 调用 `_set_auth_cookie_on_response(response, token)`
  - 确保行为完全一致

- [x] **Task 3**: 修改 `wechat_user_register()` 视图添加 cookie 设置
  - 在 `return JsonResponse(res)` 之前
  - 检查 `res.get("result")` 和 `res.get("data", {}).get("token")`
  - 调用 `_set_auth_cookie_on_response(response, token)`

- [x] **Task 4**: 验证
  - 运行 `cd server && make test` 确保测试通过
  - 检查 `lsp_diagnostics` 无错误

- [x] **Task 5**: 清理遗留的 `api/bk_lite_login/` URL 路由
  - `bk_lite_login` 是内部函数，不是视图，不应暴露为 URL
  - 从 `server/apps/core/urls.py` 中删除该路由
  - Web 前端未使用此接口（已验证）
