# Learnings & Decisions —— 经验与决策记录

> 来自实战、不可从代码直接推断的结论。每条标注日期;时间久了仍要先核实代码现状再套用。

## 认证与 Cookie 处理（2026-05-12）

- **Cookie 设置统一**:所有登录入口(`login()`、`wechat_user_register()`)必须用 `_set_auth_cookie_on_response()` 辅助函数设置 `bklite_token` cookie。
- **`bk_lite_login` 是内部函数**:它不是视图,只被 `login()` 视图内部调用(当 `domain != "domain.com"`)。**不应暴露为 URL 路由**。
- **登录流程**:Web 前端调用 `/api/proxy/core/api/login/` → 后端 `login()` 视图 → 按 domain 调用 `SystemMgmt.login()` 或 `bk_lite_login()` → 统一设置 cookie。

> 相关安全约定见 [安全红线 §2](../governance/security.md)。

---

> 新增格式:`## <主题>(YYYY-MM-DD)` + 要点。重大架构选择请改用 ADR(见 [index.md](index.md))。
