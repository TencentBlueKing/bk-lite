# Tasks: 统一登录入口的 Cookie 设置

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
