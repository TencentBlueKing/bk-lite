# Historical Superpowers change: 2026-07-03-oauth-callback-frontend-origin-declaration

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-07-03-oauth-callback-frontend-origin-declaration-design.md

**作者：** Agent (Claude Code)
**日期：** 2026-07-03
**项目：** bk-lite
**涉及产品：** 系统管理 / 集成中心 / 第三方登录认证
**对应基线：** 上一轮「OAuth 回调 URL 拼接统一」(commit pending,见 `server/apps/core/services/login_auth_request_service.py:30-48` & `server/apps/core/tests/views/test_login_auth_bindings.py` 新增的三条 service 层用例)

---

## 0. 范围与读者

- **范围**：让 OAuth 的两个绝对 URL 生成函数同时支持「前端声明 origin + 后端严格同源校验」的新契约，覆盖 callback URL(给 OAuth provider 的 `redirect_uri`)与 callback 完成后回跳到前端结果页(`/auth/signin/login-auth-result`)两条链路。
- **读者**：后端(Django service + view)、前端(Next.js `useLoginAuthValidation.ts`)、测试(单测 + e2e)。
- **不**在本 spec 范围：
  - 集成详情页 `login_auth_callback_url` 的展示语义(已在上一轮解决);
  - 微信旧链路(`OLD_WECHAT_LOGIN_CHAIN.md` 列的兼容层移除);
  - 任何 `.env` / `envs/.env.node.example` 改动(**严格不动**);
  - 多 provider adapter 实现细节(`feishu.py` 等不需要改)。

---

## 1. 背景与现状

### 1.1 上一轮的产出(基线)

上一轮已统一 OAuth callback URL 拼接为单一函数 `server/apps/core/services/login_auth_request_service.py:get_login_auth_callback_uri(request)`,逻辑是:

1. `DEFAULT_ZONE_VAR_NODE_SERVER_URL`(env)
2. `request.build_absolute_uri(...)`(同源部署时正确)
3. 空字符串

测试:`server/apps/core/tests/views/test_login_auth_bindings.py:TestLoginAuthRequestService` 现共有 3 条用例覆盖上述分支。

**剩余缺口**:
- `request.build_absolute_uri(...)` 在「dev 分端口」(Django 8011 / Next.js 3000)下给出 8011 端口,导致 dev 模式下 callback 后回跳落到 Django → Django 404 Next.js 路由。
- 没有暴露任何方式让前端告诉后端「我希望的 host:port」,只能依赖 env 兜底。

### 1.2 痛点

| # | 场景 | 痛点 |
|---|---|---|
| 1 | dev mode(Django 8011 / Next.js 3000 分端口) | 浏览器访问 3000 触发 OAuth,callback 落到 8011,callback 后回跳相对路径停留在 8011,Django 不认识前端路由,404 |
| 2 | 灰度 / 多域名 / 蓝绿部署 | 后端 env 只能配一个 `DEFAULT_ZONE_VAR_NODE_SERVER_URL`,无法同时给多个域生效 |
| 3 | 调试部署拓扑 | 走错路径要改 env + 重启 server,迭代慢 |

### 1.3 改造目标

| # | 目标 | 验收点 |
|---|---|---|
| **G1** | OAuth callback URL 与 callback 后回跳 URL 都支持「前端声明 origin + 后端同源校验」 | `start_login_auth` 接收可选 `redirect_origin`,两个 URL 生成函数优先信任声明,通过同源校验 |
| **G2** | 同源校验严格,防止 Open Redirector | `validate_redirect_origin` 拒绝跨 host / 不同端口 / 含 path/query / 非 http(s) scheme |
| **G3** | 降级路径完全保留 | 同源校验失败 / 未传 origin → 退回原 env → request → 空,行为零变化(对未升级前端 100% 兼容) |
| **G4** | 配置依赖只减不增 | **不**新增 env 变量,沿用上一轮的 `DEFAULT_ZONE_VAR_NODE_SERVER_URL` 兜底 |
| **G5** | 测试覆盖 | 新增代码 100% 行覆盖,关键边界同源校验通过 / 失败 / 多形态 origin 都有用例 |
| **G6** | 渐进可发布 | 前端 / 后端可分别升级,旧版本彼此仍可工作 |

---

## 2. 详细设计

### 2.1 新公共函数:`validate_redirect_origin(request, redirect_origin) -> bool`

```python
# server/apps/core/services/login_auth_request_service.py

def validate_redirect_origin(request, redirect_origin: str) -> bool:
    """同源校验:浏览器声明的 origin 是否可信任。

    防止 OAuth open-redirector phishing:前端只能声明与请求同源的 origin,
    不同源时调用方需降级到 env/request 兑底。
    request.get_host() 自动处理 X-Forwarded-Host,反代场景下可信。
    """
    if not redirect_origin or not isinstance(redirect_origin, str):
        return False
    try:
        parsed = urlparse(redirect_origin)
    except (ValueError, TypeError):
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:        # 必须含 host[:port]
        return False
    if parsed.path not in ("", "/"):  # 只接受纯 origin,拒绝带 path/query/fragment
        return False
    if parsed.query or parsed.fragment:
        return False
    return parsed.netloc == request.get_host()
```

**同源定义**:`parsed.netloc == request.get_host()`,其中 `request.get_host()` 内置 Django 行为:优先读 `X-Forwarded-Host` 头,再回落到 `Host` 头。生产反代正常配置时可与浏览器访问 origin 对齐。

### 2.2 `get_login_auth_callback_uri` 重载

```python
def get_login_auth_callback_uri(
    request=None,
    redirect_origin: str | None = None,
) -> str:
    """OAuth provider 的 redirect_uri 生成。

    优先级:① redirect_origin(同源校验通过)→ ② env DEFAULT_ZONE_VAR_NODE_SERVER_URL
            → ③ request → ④ 空
    """
    base_url = (os.getenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "") or "").strip().rstrip("/")
    if (
        redirect_origin
        and request is not None
        and validate_redirect_origin(request, redirect_origin)
    ):
        return f"{redirect_origin.rstrip('/')}{LOGIN_AUTH_CALLBACK_PATH}"
    if base_url:
        return f"{base_url}{LOGIN_AUTH_CALLBACK_PATH}"
    if request is not None:
        return request.build_absolute_uri(LOGIN_AUTH_CALLBACK_PATH)
    return ""
```

**与上一轮的兼容性**:旧调用方不传 `redirect_origin` 时,函数语义完全等价(只是新增了一个不影响结果的字段)。

### 2.3 `create_auth_request` 增加 `redirect_origin` 字段

```python
def create_auth_request(
    binding_id: int,
    provider_key: str,
    callback_url: str,
    redirect_origin: str | None = None,
) -> dict:
    """创建登录认证请求,缓存到 backend cache。

    新增可选字段 redirect_origin:跨过 OAuth 跳转传给 callback 后的回跳函数。
    """
    auth_request_id = str(uuid.uuid4())
    poll_token = str(uuid.uuid4())
    ...
    auth_request = {
        "auth_request_id": auth_request_id,
        "poll_token": poll_token,
        "binding_id": binding_id,
        "provider_key": provider_key,
        "callback_url": callback_url,
        "redirect_origin": redirect_origin or "",
        "status": "pending",
        ...
    }
```

字段顺序调整无影响;`auth_request` dict 共享给 `get_auth_request` 与 `update_auth_request_status`,后两者**不**需要改签名。

### 2.4 `_build_login_auth_result_redirect` 签名扩展

文件:`server/apps/core/views/index_view.py`

```python
def _build_login_auth_result_redirect(
    request,
    status_key: str,
    message: str,
    redirect_origin: str | None = None,
) -> HttpResponseRedirect:
    """OAuth callback 完成后回跳前端结果页。

    优先级:① redirect_origin(同源校验通过)→ ② 相对路径兑底
    """
    path = f"/auth/signin/login-auth-result?{urlencode({'status': status_key, 'message': message})}"
    if (
        redirect_origin
        and validate_redirect_origin(request, redirect_origin)
    ):
        return HttpResponseRedirect(f"{redirect_origin.rstrip('/')}{path}")
    return HttpResponseRedirect(path)
```

### 2.5 `start_login_auth` 解析入参 + 透传

文件:`server/apps/core/views/index_view.py:start_login_auth`

```python
@api_exempt
def start_login_auth(request):
    if request.method != "POST":
        return JsonResponse({"result": False, "message": "Method not allowed"}, status=405)

    try:
        data = _parse_request_data(request)
        callback_url = (data.get("callback_url") or "/").strip() or "/"
        binding_id = data.get("binding_id")
        redirect_origin = (data.get("redirect_origin") or "").strip() or None  # 新增

        if not _is_safe_relative_callback_url(callback_url):
            return JsonResponse({"result": False, "message": "callback_url must be an in-site relative path"}, status=400)

        try:
            binding_id = int(binding_id)
        except (TypeError, ValueError):
            return JsonResponse({"result": False, "message": "binding_id is required"}, status=400)

        binding = _get_login_auth_binding_by_id(binding_id)
        if not binding:
            return JsonResponse({"result": False, "message": "Login auth binding not found"}, status=404)

        auth_request = create_auth_request(
            binding_id=binding.id,
            provider_key=binding.integration_instance.provider_key,
            callback_url=callback_url,
            redirect_origin=redirect_origin,    # 新增
        )
        state = build_auth_request_state(...)
        redirect_result = build_login_auth_redirect(
            binding,
            redirect_uri=get_login_auth_callback_uri(request=request, redirect_origin=redirect_origin),  # 改
            state=state,
        )
        ...
```

### 2.6 `login_auth_callback` 8 处调用点统一改造

文件:`server/apps/core/views/index_view.py:login_auth_callback`

```python
@api_exempt
def login_auth_callback(request):
    state = request.GET.get("state", "").strip()
    code = request.GET.get("code", "").strip()
    provider_error = request.GET.get("error", "").strip()
    error_description = request.GET.get("error_description", "").strip()

    state_payload = parse_auth_request_state(state)
    if not state_payload:
        return _build_login_auth_result_redirect(request, "failed", "认证状态无效或已过期...")  # +request

    auth_request_id = state_payload["auth_request_id"]
    auth_request = get_auth_request(auth_request_id)
    if not auth_request:
        return _build_login_auth_result_redirect(request, "expired", "认证请求已过期...")  # +request

    # 集中读一次
    redirect_origin = (auth_request or {}).get("redirect_origin") or None

    current_status = auth_request.get("status", "pending")
    if current_status != "pending":
        ...
        return _build_login_auth_result_redirect(
            request,                                       # +request
            current_status,
            terminal_messages.get(current_status, "..."),
            redirect_origin=redirect_origin,                # 新增
        )

    if provider_error:
        message = error_description or provider_error
        update_auth_request_status(auth_request_id, status="cancelled", error_message=message)
        return _build_login_auth_result_redirect(request, "cancelled", "...", redirect_origin=redirect_origin)  # 改

    if not code:
        update_auth_request_status(auth_request_id, status="failed", error_message="Missing provider code")
        return _build_login_auth_result_redirect(request, "failed", "...", redirect_origin=redirect_origin)

    try:
        client = SystemMgmt()
        result = client.login_with_binding(state_payload["binding_id"], code)
    except Exception as e:
        logger.error(f"Login auth callback error: {e}")
        update_auth_request_status(auth_request_id, status="failed", error_message=str(e))
        return _build_login_auth_result_redirect(request, "failed", "...", redirect_origin=redirect_origin)

    if not result.get("result"):
        error_message = result.get("message", "Login auth callback failed")
        update_auth_request_status(auth_request_id, status="failed", error_message=error_message)
        return _build_login_auth_result_redirect(request, "failed", "...", redirect_origin=redirect_origin)

    login_result = result.get("data", {}) or {}
    login_result.setdefault("redirect_url", state_payload["callback_url"])
    update_auth_request_status(
        auth_request_id,
        status="success",
        login_result=login_result,
    )

    response = _build_login_auth_result_redirect(request, "success", "...", redirect_origin=redirect_origin)  # 改
    if login_result.get("token"):
        _set_auth_cookie_on_response(response, login_result["token"])
    return response
```

**8 处分布**:
- 2 处(state 解析失败 / auth_request cache miss):在拿到 auth_request 之前 return,`redirect_origin=None` 走相对路径(契约不变)。
- 6 处(终态重放 / 取消 / 缺 code / 系统异常 / login_with_binding 失败 / success):从 cache 读出 origin,做同源校验,通过则用绝对 URL。

> 注:测试只需覆盖 "origin 同源 / origin 跨 host / origin 缺失" 三种条件组合,不必为每个 status 分支单写一条用例——6 个 status 分支共用同一段 `_build_login_auth_result_redirect` 调用,集成行为已被覆盖。

### 2.7 前端改动

文件:`web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts:246-249`

```diff
       body: JSON.stringify({
         binding_id: binding.id,
         callback_url: safeCallbackUrl,
+        redirect_origin: window.location.origin,
       }),
```

单点 1 行改动,语义自解释(`window.location.origin` 浏览器权威,无法被中间件改写)。

---

## 3. 数据流(同源部署 + dev 分端口两种场景)

### 3.1 生产同源部署(反代正常配置 X-Forwarded-Host)

```
浏览器 https://example.com/auth/signin
  POST /api/v1/core/api/start_login_auth/
    {binding_id, callback_url, redirect_origin: "https://example.com"}
  Host: example.com, X-Forwarded-Proto: https

→ Django request.get_host() = "example.com" (经 X-Forwarded-Host)
→ validate_redirect_origin(.., "https://example.com") = True
→ get_login_auth_callback_uri 用声明 origin 返回:
  "https://example.com/api/v1/core/api/login_auth/callback/"
→ Provider 授权后回调这个 URL,反代再带 X-Forwarded-Host 到 Django
→ Django _build_login_auth_result_redirect 用 cache 中的 origin,同源通过
→ 302 到 "https://example.com/auth/signin/login-auth-result?status=success&..."
```

### 3.2 dev 分端口(无反代,浏览器直连 8011)

```
浏览器 http://10.10.40.56:3000/auth/signin
  POST /api/v1/core/api/start_login_auth/
    {binding_id, callback_url, redirect_origin: "http://10.10.40.56:3000"}

→ Django 监听 8011,request.get_host() = "10.10.40.56:8011"
→ validate_redirect_origin(.., "10.10.40.56:3000") = False (跨端口)
→ get_login_auth_callback_uri 降级到 env:
  .env 当前值 "http://10.10.40.56:443"
  → "http://10.10.40.56:443/api/v1/core/api/login_auth/callback/"
→ Provider 回调 443(需基础设施可达)
→ callback view 中,request.get_host() = "10.10.40.56:443"(由 Provider / 反代给的)
  假设 validate_redirect_origin(.., "http://10.10.40.56:3000"):
  若反代设置 X-Forwarded-Host: 10.10.40.56:3000 → 通过 → 3000 拼接
  否则 host = 10.10.40.56:443 → 校验失败 → 相对路径兑底
```

**关键含义**:
- **发起阶段** 在无反代 dev 下仍走 env 兑底(本次不动这一阶段)
- **回调后回跳阶段** 在反代设置 X-Forwarded-Host 时通过;否则降级相对路径
- dev 完整通路仍依赖基础设施(nginx / caddy 反代在 10.10.40.56 监听 443 → 上游 8011 + 3000,带 X-Forwarded-Host),但**架构不再要求运维修改 `.env`** —— 这是本次目标的核心收益

### 3.3 auth_request 生命周期

```
create_auth_request (TTL=300s)
  ├── binding_id, provider_key, callback_url, redirect_origin
  │
  │ [300s 内 OAuth 跳转]
  │
callback view
  ├── cache.get → auth_request dict
  ├── redirect_origin = auth_request.get("redirect_origin")  [空 → None]
  └── 校验 / 拼 URL
```

`update_auth_request_status` 不修改 `redirect_origin`,所以后续 status 切换(cancelled / expired 等)仍能读到发起时的原始声明(可能因 host 变更导致校验失败,降级)。

---

## 4. 错误处理与可观测性

### 4.1 输入校验失败 → 静默降级

| 异常 | 处理 |
|---|---|
| `redirect_origin` 缺失 / 空字符串 / 非字符串 | 跳过同源分支,降级到 env |
| `redirect_origin` 含 `path`/`query`/`fragment` | 同源校验 False → 降级 + warning 日志 |
| `redirect_origin` scheme 非 http/https | 同源校验 False → 降级 + warning 日志 |
| `redirect_origin` 跨 host / 不同端口 | 同源校验 False → 降级 + warning 日志 |

降级不返 4xx:前端声明错误是合法调用,只是没拿到声明的权限,降级到 env/request 是对前端的合理响应。

### 4.2 失败日志规范

```python
# 在 validate_redirect_origin 内部,失败分支记录 warning
logger.warning(
    "login_auth: redirect_origin rejected: "
    "expected_host=%s actual_host=%s reason=%s",
    request.get_host(),
    parsed.netloc,
    failure_reason,  # "scheme" / "netloc" / "path" / "query" / "fragment"
)
```

**不打印 origin 全文** —— 最小化日志体积 / 减少 host 探测信息泄漏。运维通过频次发现异常,通过 `failure_reason` 区分误用类型。

### 4.3 已有错误响应契约

| 错误 | HTTP | 文本 | 本次影响 |
|---|---|---|---|
| callback_url 非相对路径 | 400 | "callback_url must be an in-site relative path" | 不变(与 origin 正交) |
| binding_id 缺失 | 400 | "binding_id is required" | 不变 |
| binding 未找到 | 404 | "Login auth binding not found" | 不变 |
| 业务断言失败 | 400 / 500 | 沿用 | 不变 |
| OAuth 错误(取消 / 缺 code / 系统异常 / 业务失败) | 302 到结果页 | 沿用 | 不变(redirect URL 拼接策略变了,文案不变) |

`start_login_auth` 成功响应 JSON 形状不变;新增可选入参不影响调用方兼容(旧前端不传,新前端传)。

---

## 5. 测试计划

### 5.1 单测矩阵

文件:`server/apps/core/tests/views/test_login_auth_bindings.py`

| Class | 用例名(伪代码) | 输入 | 期望 |
|---|---|---|---|
| TestLoginAuthRequestService | test_validate_redirect_origin_accepts_same_origin | host=`bk.test:3000`, origin=`http://bk.test:3000` | True |
| TestLoginAuthRequestService | test_validate_redirect_origin_accepts_origin_via_x_forwarded_host | env 设 `HTTP_X_FORWARDED_HOST=bk.test:3000`, origin=`https://bk.test:3000` | True |
| TestLoginAuthRequestService | test_validate_redirect_origin_rejects_cross_port | host=`bk.test:8011`, origin=`http://bk.test:3000` | False |
| TestLoginAuthRequestService | test_validate_redirect_origin_rejects_cross_host | origin=`http://other.com` | False |
| TestLoginAuthRequestService | test_validate_redirect_origin_rejects_with_path | origin=`http://bk.test/x` | False |
| TestLoginAuthRequestService | test_validate_redirect_origin_rejects_with_query | origin=`http://bk.test?x=1` | False |
| TestLoginAuthRequestService | test_validate_redirect_origin_rejects_with_fragment | origin=`http://bk.test#y` | False |
| TestLoginAuthRequestService | test_validate_redirect_origin_rejects_non_http_scheme | scheme=`javascript:` | False |
| TestLoginAuthRequestService | test_validate_redirect_origin_rejects_empty_or_invalid | `""` / `None` / 非字符串 | False |
| TestLoginAuthRequestService | test_get_login_auth_callback_uri_prefers_validated_redirect_origin | origin 同源 + env 也在 | 返回 origin 拼接 |
| TestLoginAuthRequestService | test_get_login_auth_callback_uri_falls_back_to_env_when_origin_rejected | origin 跨 host + env 也在 | 返回 env 拼接 |
| TestLoginAuthRequestService | test_get_login_auth_callback_uri_preserves_existing_behavior_when_no_origin | origin=None + env/request 都走原分支 | 沿用既有断言 |
| TestLoginAuthRequestService | test_create_auth_request_stores_redirect_origin_field | create with redirect_origin | dict 含该字段,cache 可读出 |
| TestLoginAuthBindingViews | test_build_login_auth_result_redirect_prefers_validated_origin | 同源 | 302 absolute |
| TestLoginAuthBindingViews | test_build_login_auth_result_redirect_falls_back_to_relative_when_origin_rejected | 跨 host | 302 relative |
| TestLoginAuthBindingViews | test_build_login_auth_result_redirect_uses_relative_when_origin_missing | origin=None | 302 relative(沿用契约) |
| TestLoginAuthBindingViews | test_start_login_auth_passes_validated_redirect_origin_to_build_redirect | POST with origin | mock_build_redirect 收到 origin 拼接 URI |
| TestLoginAuthBindingViews | test_start_login_auth_compatible_when_origin_missing | POST no origin | mock 收到 env 兜底 URI(兼容老前端) |
| TestLoginAuthBindingViews | test_login_auth_callback_prefers_redirect_origin_on_success_terminal | cache 有 origin(同源) | 302 to absolute |
| TestLoginAuthBindingViews | test_login_auth_callback_falls_back_to_relative_when_origin_rejected | cache 有 origin(跨 host) | 302 to relative |
| TestLoginAuthBindingViews | test_login_auth_callback_handles_missing_origin_for_legacy_state | cache 无 origin | 302 to relative(契约不变) |

**总计:21 条新用例;既有 ~10 条用例保持原状、不需要改(沿用上一轮已加的 fallback / env / 等用例,断言兼容)。**

### 5.2 覆盖目标

| 范围 | 行覆盖率 |
|---|---|
| `login_auth_request_service.py`(`validate_redirect_origin` + `get_login_auth_callback_uri` 新分支 + `create_auth_request` 新字段) | **100%**(新代码) |
| `index_view.py`(`start_login_auth` + 8 处 `_build_login_auth_result_redirect` 调用) | 不降低现有覆盖;关键路径(redirect_origin 拼接与降级)100% |
| 整体 `login_auth_request_service.py` | ≥75%(沿用项目阈值) |

### 5.3 非测试相关的验证

| 项 | 命令 |
|---|---|
| 后端门禁 | `cd server && make test`(已含现有 27+ 个相关用例) |
| 前端类型检查 | `cd web && pnpm type-check` |
| 前端 lint | `cd web && pnpm lint` |
| env 未改检查 | `git diff server/.env server/envs/.env.node.example` 应为空 |

---

## 6. 文件改动清单

| 路径 | 改动类型 | 行数预估 |
|---|---|---|
| `server/apps/core/services/login_auth_request_service.py` | 改:新增 `validate_redirect_origin` + 扩 `get_login_auth_callback_uri` 与 `create_auth_request` 签名 | ~+30 行 |
| `server/apps/core/views/index_view.py` | 改:`start_login_auth` 加 1 入参 + 2 处透传;`_build_login_auth_result_redirect` 加 2 参数;8 处调用点同步改 | ~+30 行 |
| `server/apps/core/tests/views/test_login_auth_bindings.py` | 增 20 条新用例 + 更新 0 条既有用例 | ~+250 行 |
| `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts` | 增 1 个字段 | +1 行 |

**总计**:后端 ~60 行代码 + 250 行测试,前端 +1 行。

**不动**:
- `server/.env`
- `server/envs/.env.node.example`
- `server/apps/core/urls.py`
- 任何 adapter(`feishu.py` 等)
- 集成详情页 `integration_instance_serializer.py`(上一轮已完成)

---

## 7. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| `request.get_host()` 因 X-Forwarded-Host 配置缺失,导致同源校验系统性失败,所有 dev 环境退化为相对路径 | 中(老部署) | 低(降级到现状) | 仅 dev 出现;生产正常反代配置无影响;CLI 频次 surge 可观测 |
| `validate_redirect_origin` 误把合法 origin 拒绝(比如协议不一致 `ws://` vs `http://`) | 低 | 低 | 仅覆盖 http/https;现有 OAuth provider 只用这两 |
| `redirect_origin` 字段泄漏到日志 | 中 | 中 | 失败日志**不打印 origin 全文**,仅记 reason / host 名 |
| 多 provider 时 `redirect_origin` 行为差异 | 低 | 低 | origin 与 provider 无关;走同一套拼接 |
| 老前端 (未传 `redirect_origin`) 线上回退到 dev 404 | 低 | 中 | 本次前端单点同步改,前后端一起发版即可;逐版本可分开但建议同步 |
| 当前 `auth_request` cache 不分租户,redirect_origin 在 TTL 内被另一会话读到 | 极低 | 低 | cache key 以 `auth_request_id` 唯一,同一 id 不能跨会话;安全性由 state signature 保证 |

---

## 8. 迁移计划

1. 后端先合入:`validate_redirect_origin` + 函数签名扩展 + 测试,确保 `make test` 全绿。
2. 前端单点同步合入 `useLoginAuthValidation.ts:redirect_origin` 一行。
3. 部署:无顺序要求(两端独立可工作),但端到端验证需两端都已发布。
4. 端到端验证清单:
   - 同源部署(测试或 staging):发起 → callback → 回跳结果页,断言回跳 URL 是 `https://<host>/auth/signin/...`
   - dev 分端口(无反代):发起阶段使用 env 兜底;回跳阶段降级相对路径(应保留现状)
   - 跨 host 攻击模拟:把 `redirect_origin` 改成 `evil.com`,断言 callback 后回跳仍是相对路径,**不**跳到 `evil.com`

---

## 9. 未来延伸

不在本次范围,但本契约为以下演进铺路:

1. **多域名 / 灰度**:增加 `REDIRECT_ORIGIN_ALLOWLIST` env(默认空,白名单逻辑在 `validate_redirect_origin` 增加第二阶段校验)—— 把本次的「严格同源」从「允许同源 + 显式 allowlist」两步走。
2. **微信接入新架构**:微信走与飞书一样的 start / callback 抽象,把 `WechatQrLoginPanel.tsx` 的 `window.location.origin` 直接传 `redirect_origin`,删除 `OLD_WECHAT_LOGIN_CHAIN.md` 中残留兼容层。
3. **`_build_login_auth_result_redirect` 接受 origin 但不传时降级**:本次已实现;后续若发现更多旧链路(如邮件激活、短信验证)使用同样模式,可横向迁移。
