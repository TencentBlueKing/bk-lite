# Historical Superpowers change: 2026-07-03-oauth-callback-frontend-origin

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-03-oauth-callback-frontend-origin.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让前端 `start_login_auth` 携带 `window.location.origin`,后端在生成 OAuth callback URL 与 callback 完成后的回跳 URL 时严格同源校验,dev 分端口与多域名拓扑下不再依赖 `DEFAULT_ZONE_VAR_NODE_SERVER_URL` 兜底。

**Architecture:** 后端 `login_auth_request_service.py` 新增 `validate_redirect_origin()` 纯函数,把它塞进 `get_login_auth_callback_uri()` 的优先级链首;同时把 `redirect_origin` 存进 `auth_request` 缓存 TTL=300s,callback view 集中读取后传入 `_build_login_auth_result_redirect()` 复用同一套同源校验。前端 1 个调用点(`useLoginAuthValidation.ts`)多带一个字段。

**Tech Stack:** Django 4.2 / Python 3.12 / pytest + RequestFactory / Next.js 16 / TypeScript;环境变量通过 `python-dotenv` 加载;OAuth 缓存走 `django.core.cache`。

## Global Constraints

从 `AGENTS.md` 与本 spec 提取的硬约束,每个任务的隐含前提:

- **中文优先**:回答、注释、commit、文档一律中文。
- **测试红线**:新功能先写测试(TDD 红-绿-重构);改动代码覆盖率 ≥75%;测行为不测实现。
- **禁用原生 SQL**:不走 raw SQL / `.raw()` / `RawSQL`,统一走 Django ORM。
- **最小 diff**:不动与需求无关的文件与代码块。
- **不变项**(本 spec 范围内严格不动):
  - `server/.env`
  - `server/envs/.env.node.example`
  - `server/apps/core/urls.py`
  - 任何 adapter(`feishu.py` / `wechat.py`)
  - 集成详情页 `integration_instance_serializer.py`(上一轮已落地)
- **后端门禁**:`cd server && make test`(已含现成 27+ 相关用例,新代码 100% 覆盖)。
- **前端门禁**:`cd web && pnpm type-check && pnpm lint`。

---

### Task 1: `validate_redirect_origin` 单元测试 (RED)

**Files:**
- Modify: `server/apps/core/tests/views/test_login_auth_bindings.py` (在 `TestLoginAuthRequestService` 类末尾追加 9 条用例)
- Test: 同上

**Interfaces:**
- Consumes: 既有 `TestLoginAuthRequestService` 类、`_load_login_auth_request_service` helper、`RequestFactory`。
- Produces: 一个新的公共函数 `validate_redirect_origin(request, redirect_origin: str) -> bool`,后续 Task 2 实现,后续 Task 3-10 全部依赖它。

> 本任务只写测试,**不**写实现,保证 RED。

- [ ] **Step 1: 写 9 条失败测试**

在文件 `server/apps/core/tests/views/test_login_auth_bindings.py` 的 `TestLoginAuthRequestService` 类的 `test_get_login_auth_callback_uri_returns_empty_when_env_and_request_missing` 之后,追加:

```python
class TestValidateRedirectOrigin:
    """validate_redirect_origin 纯函数同源校验测试。

    覆盖 host 与 origin 的各种关系以及 origin 字段合法性。
    """

    def _load_service(self):
        return _load_login_auth_request_service()

    def test_accepts_same_origin_host_and_port(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test:3000"

        assert service.validate_redirect_origin(request, "http://bk.test:3000") is True

    def test_accepts_https_origin_via_x_forwarded_host(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_X_FORWARDED_HOST"] = "bk.test"
        request.META["HTTP_X_FORWARDED_PROTO"] = "https"

        assert service.validate_redirect_origin(request, "https://bk.test") is True

    def test_rejects_cross_port_between_origin_and_request_host(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test:8011"

        assert service.validate_redirect_origin(request, "http://bk.test:3000") is False

    def test_rejects_cross_host(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "a.example"

        assert service.validate_redirect_origin(request, "http://b.example") is False

    def test_rejects_origin_with_path(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test"

        assert service.validate_redirect_origin(request, "http://bk.test/console") is False

    def test_rejects_origin_with_query(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test"

        assert service.validate_redirect_origin(request, "http://bk.test?x=1") is False

    def test_rejects_origin_with_fragment(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test"

        assert service.validate_redirect_origin(request, "http://bk.test#anchor") is False

    def test_rejects_non_http_scheme(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test"

        assert service.validate_redirect_origin(request, "javascript:alert(1)") is False
        assert service.validate_redirect_origin(request, "file:///etc/passwd") is False

    def test_rejects_empty_or_non_string_or_missing_netloc(self):
        service = self._load_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test"

        assert service.validate_redirect_origin(request, "") is False
        assert service.validate_redirect_origin(request, None) is False
        assert service.validate_redirect_origin(request, 123) is False
        assert service.validate_redirect_origin(request, "http://") is False
```

- [ ] **Step 2: 跑测试确认 RED**

```bash
cd /Users/lanyu/Work/bk-lite/server && \
  uv run pytest apps/core/tests/views/test_login_auth_bindings.py::TestValidateRedirectOrigin --no-header --no-cov -v 2>&1 | tail -25
```

预期:`9 failed`,每条都是 `AttributeError: module 'apps.core.services.login_auth_request_service' has no attribute 'validate_redirect_origin'` 或 `ImportError`。**不要试图修复——这是 RED 的标志。**

- [ ] **Step 3: 不创建 commit**

按 TDD 红-绿-重构,**测试失败时不能 commit**。跳到 Task 2 实现。

---

### Task 2: `validate_redirect_origin` 实现 (GREEN)

**Files:**
- Modify: `server/apps/core/services/login_auth_request_service.py` (顶部 `from urllib.parse import urlparse`,在 `get_login_auth_callback_uri` 上方新增函数)

**Interfaces:**
- Consumes: `urlparse` 标准库、`request.META["HTTP_HOST"]` 与 `HTTP_X_FORWARDED_HOST`。
- Produces: 公共函数 `validate_redirect_origin(request, redirect_origin: str) -> bool`,签名与 Task 1 测试一致。

- [ ] **Step 1: 加 `validate_redirect_origin` 实现**

修改 `server/apps/core/services/login_auth_request_service.py`:

- **第 5 行** 把 `from urllib.parse import urlparse` 加回来(如果 Task 1 之外有别处去掉过,这里确保存在)。
- 在 `LOGIN_AUTH_CALLBACK_PATH` 之后、`get_login_auth_callback_uri` 之前,新增:

```python
def validate_redirect_origin(request, redirect_origin) -> bool:
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
    if not parsed.netloc:
        return False
    if parsed.path not in ("", "/"):
        return False
    if parsed.query or parsed.fragment:
        return False
    return parsed.netloc == request.get_host()
```

- [ ] **Step 2: 跑测试确认 GREEN**

```bash
cd /Users/lanyu/Work/bk-lite/server && \
  uv run pytest apps/core/tests/views/test_login_auth_bindings.py::TestValidateRedirectOrigin --no-header --no-cov -v 2>&1 | tail -15
```

预期:`9 passed`。

- [ ] **Step 3: 跑既有用例确认未破坏**

```bash
cd /Users/lanyu/Work/bk-lite/server && \
  uv run pytest apps/core/tests/views/test_login_auth_bindings.py --no-header --no-cov -q 2>&1 | tail -10
```

预期:全部 PASSED(既有 ~36 条 + 新增 9 条)。

- [ ] **Step 4: commit**

```bash
cd /Users/lanyu/Work/bk-lite && \
  git add server/apps/core/services/login_auth_request_service.py \
         server/apps/core/tests/views/test_login_auth_bindings.py && \
  git -c user.name="Claude" -c user.email="noreply@anthropic.com" commit -m "$(cat <<'EOF'
feat(server-core): 新增 validate_redirect_origin 同源校验函数

OAuth 流程中,允许前端在 start_login_auth 时声明 window.location.origin,
后端通过 validate_redirect_origin 严格校验其与请求是否同源,
防止 open redirector phishing。

- 仅信任 HTTP/HTTPS scheme 的纯 origin
- 拒绝含 path / query / fragment 的输入
- 拒绝空值与非字符串
- 通过 = parsed.netloc == request.get_host()
  (后者自动处理 X-Forwarded-Host,反代场景下可信)

附 9 条单测覆盖以上全部边界。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `get_login_auth_callback_uri` 重载单元测试 (RED)

**Files:**
- Modify: `server/apps/core/tests/views/test_login_auth_bindings.py` (在 `TestLoginAuthRequestService` 类末尾追加 3 条用例)

**Interfaces:**
- Consumes: Task 2 的 `validate_redirect_origin`。
- Produces: 修改后的 `get_login_auth_callback_uri` 签名 `def get_login_auth_callback_uri(request=None, redirect_origin: str | None = None) -> str`。

- [ ] **Step 1: 写 3 条失败测试**

在文件 `server/apps/core/tests/views/test_login_auth_bindings.py` 的 `TestValidateRedirectOrigin` 类之前,或 `TestLoginAuthRequestService` 类末尾追加:

```python
    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "http://bk.test:443"}, clear=False)
    def test_get_login_auth_callback_uri_prefers_validated_redirect_origin_over_env(self):
        service = _load_login_auth_request_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test:3000"

        # 即使 env 配了 :443,前端声明的同源 :3000 胜出
        assert service.get_login_auth_callback_uri(
            request=request,
            redirect_origin="http://bk.test:3000",
        ) == "http://bk.test:3000/api/v1/core/api/login_auth/callback/"

    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "http://bk.test:443"}, clear=False)
    def test_get_login_auth_callback_uri_falls_back_to_env_when_origin_rejected(self):
        service = _load_login_auth_request_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test:8011"

        # origin 跨端口(8011 vs 3000)被同源校验拒绝,降级到 env
        assert service.get_login_auth_callback_uri(
            request=request,
            redirect_origin="http://bk.test:3000",
        ) == "http://bk.test:443/api/v1/core/api/login_auth/callback/"

    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "http://bk.test:443"}, clear=False)
    def test_get_login_auth_callback_uri_legacy_behavior_when_no_origin(self):
        service = _load_login_auth_request_service()
        request = RequestFactory().get("/api/v1/core/api/start_login_auth/")
        request.META["HTTP_HOST"] = "bk.test:8011"

        # 不传 redirect_origin 时,完全沿用上一轮既有的 env 兑底行为
        assert service.get_login_auth_callback_uri(request=request) == (
            "http://bk.test:443/api/v1/core/api/login_auth/callback/"
        )
```

> 注:这 3 条函数应当插入到 `TestLoginAuthRequestService` 类内部(因为它们引用 `self._load_service` 不必要,且与该类其它用例签名一致)。或者用一个独立的 `TestGetLoginAuthCallbackUriWithRedirectOrigin` 类包裹。**根据文件现有风格选择**——查看该文件中 `TestLoginAuthRequestService` 是否所有用例都直接是 `def test_xxx(self):` 不带装饰器,若是则直接追加到该类末尾,与既存 3 条用例并列。

- [ ] **Step 2: 跑测试确认 RED**

```bash
cd /Users/lanyu/Work/bk-lite/server && \
  uv run pytest apps/core/tests/views/test_login_auth_bindings.py \
    -k "prefers_validated_redirect_origin_over_env or falls_back_to_env_when_origin_rejected or legacy_behavior_when_no_origin" \
    --no-header --no-cov -v 2>&1 | tail -20
```

预期:前 2 条会因 `redirect_origin` 参数未被函数接受而失败(`TypeError` 或断言不符)。第 3 条会 PASS(因为现状本来就支持 request+env 调用)。

如第 3 条意外失败——把期望值与既有返回对照确认,可能 `request.build_absolute_uri` 受 `HTTP_HOST=bk.test:8011` 影响给出 `http://bk.test:8011/...`(端口带冒号),需要仔细比对。**若断言形式与现状不一致,以现状为准(本条本就是"保留旧行为"用例,期望值应调整为现状实测值)。**

- [ ] **Step 3: 不创建 commit**

---

### Task 4: `get_login_auth_callback_uri` 重载实现 (GREEN)

**Files:**
- Modify: `server/apps/core/services/login_auth_request_service.py`(`get_login_auth_callback_uri` 函数体)

**Interfaces:**
- Consumes: Task 2 的 `validate_redirect_origin`、env `DEFAULT_ZONE_VAR_NODE_SERVER_URL`、`request.build_absolute_uri()`。
- Produces: 同上签名,新增行为分支。

- [ ] **Step 1: 重写 `get_login_auth_callback_uri` 函数体**

把 `server/apps/core/services/login_auth_request_service.py` 中的:

```python
def get_login_auth_callback_uri(request=None) -> str:
    """生成 login_auth 回调地址。...（doc 略）"""
    base_url = os.getenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "").strip().rstrip("/")
    if base_url:
        return f"{base_url}{LOGIN_AUTH_CALLBACK_PATH}"
    if request is not None:
        return request.build_absolute_uri(LOGIN_AUTH_CALLBACK_PATH)
    return ""
```

替换为:

```python
def get_login_auth_callback_uri(request=None, redirect_origin: str | None = None) -> str:
    """生成 login_auth 回调地址。

    优先级:
      1. ``redirect_origin``(同源校验通过时胜出,适用于反代/同源部署可见)
      2. 环境变量 ``DEFAULT_ZONE_VAR_NODE_SERVER_URL``
      3. ``request.build_absolute_uri(...)``(典型 dev / 反代未配置场景)
      4. 空字符串

    该函数同时用于:
      - 集成中心详情页「平台回调地址」展示
      - OAuth 启动流程中飞书/钉钉等 adapter 的 ``redirect_uri``
    """
    base_url = os.getenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "").strip().rstrip("/")
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

- [ ] **Step 2: 跑 Task 3 的 3 条测试 + Task 1 的 9 条**

```bash
cd /Users/lanyu/Work/bk-lite/server && \
  uv run pytest apps/core/tests/views/test_login_auth_bindings.py \
    -k "validate_redirect_origin or callback_uri" \
    --no-header --no-cov -v 2>&1 | tail -25
```

预期:全部 passed。

- [ ] **Step 3: 跑既有用例**

```bash
cd /Users/lanyu/Work/bk-lite/server && \
  uv run pytest apps/core/tests/views/test_login_auth_bindings.py --no-header --no-cov -q 2>&1 | tail -10
```

预期:全部 PASSED。

- [ ] **Step 4: commit**

```bash
cd /Users/lanyu/Work/bk-lite && \
  git add server/apps/core/services/login_auth_request_service.py && \
  git -c user.name="Claude" -c user.email="noreply@anthropic.com" commit -m "$(cat <<'EOF'
feat(server-core): get_login_auth_callback_uri 接受 redirect_origin

新增可选参数 redirect_origin,与 validate_redirect_origin 配合:
- 同源校验通过时胜出 env/request 兑底
- 拒绝则静默降级,行为完全向上兼容

未调用者无需改动。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `create_auth_request` 新增 `redirect_origin` 字段单测 (RED)

**Files:**
- Modify: `server/apps/core/tests/views/test_login_auth_bindings.py` (在 `TestLoginAuthRequestService` 末尾追加 1 条)

**Interfaces:**
- Consumes: 既有的 `create_auth_request` 签名 `create_auth_request(binding_id, provider_key, callback_url, ...) -> dict`,fake_cache mock pattern。
- Produces: 修改后的 `create_auth_request(binding_id, provider_key, callback_url, redirect_origin=None)`。

- [ ] **Step 1: 写 1 条失败测试**

```python
    def test_create_auth_request_stores_redirect_origin_in_cache(self):
        service = _load_login_auth_request_service()
        fake_cache = FakeCache()

        with patch.object(service, "cache", fake_cache):
            auth_request = service.create_auth_request(
                binding_id=12,
                provider_key="feishu",
                callback_url="/console",
                redirect_origin="http://bk.test:3000",
            )

        # 返回的 dict 含新字段
        assert auth_request["redirect_origin"] == "http://bk.test:3000"
        # cache 中能读出(后续 login_auth_callback 依赖此字段做回跳拼接)
        cached = service.get_auth_request(auth_request["auth_request_id"])
        assert cached["redirect_origin"] == "http://bk.test:3000"
```

- [ ] **Step 2: 跑测试确认 RED**

```bash
cd /Users/lanyu/Work/bk-lite/server && \
  uv run pytest apps/core/tests/views/test_login_auth_bindings.py::TestLoginAuthRequestService::test_create_auth_request_stores_redirect_origin_in_cache --no-header --no-cov -v 2>&1 | tail -10
```

预期:`TypeError: create_auth_request() got an unexpected keyword argument 'redirect_origin'`。

---

### Task 6: `create_auth_request` 新增 `redirect_origin` 字段实现 (GREEN)

**Files:**
- Modify: `server/apps/core/services/login_auth_request_service.py`(`create_auth_request` 函数)

**Interfaces:**
- Produces: `create_auth_request` 接受可选 `redirect_origin`,写进 auth_request dict 与 cache。

- [ ] **Step 1: 加字段**

把 `server/apps/core/services/login_auth_request_service.py` 中的 `create_auth_request`:

```python
def create_auth_request(binding_id: int, provider_key: str, callback_url: str) -> dict:
```

改为:

```python
def create_auth_request(binding_id: int, provider_key: str, callback_url: str, redirect_origin: str | None = None) -> dict:
```

并在函数体内,`auth_request = {...}` 字典中新增一行 `"redirect_origin": redirect_origin or "",`(建议放在 `"callback_url": callback_url,` 之后,保持「输入字段相邻」的可读性)。

```python
    auth_request = {
        "auth_request_id": auth_request_id,
        "poll_token": poll_token,
        "binding_id": binding_id,
        "provider_key": provider_key,
        "callback_url": callback_url,
        "redirect_origin": redirect_origin or "",
        "status": "pending",
        "error_message": "",
        ...
    }
```

- [ ] **Step 2: 跑测试确认 GREEN**

```bash
cd /Users/lanyu/Work/bk-lite/server && \
  uv run pytest apps/core/tests/views/test_login_auth_bindings.py::TestLoginAuthRequestService --no-header --no-cov -q 2>&1 | tail -10
```

预期:全部 PASSED。

- [ ] **Step 3: 跑既有相关 service 单测**

```bash
cd /Users/lanyu/Work/bk-lite/server && \
  uv run pytest apps/core/tests/views/test_login_auth_bindings.py --no-header --no-cov -q 2>&1 | tail -10
```

预期:全部 PASSED。

- [ ] **Step 4: commit**

```bash
cd /Users/lanyu/Work/bk-lite && \
  git add server/apps/core/services/login_auth_request_service.py \
         server/apps/core/tests/views/test_login_auth_bindings.py && \
  git -c user.name="Claude" -c user.email="noreply@anthropic.com" commit -m "$(cat <<'EOF'
feat(server-core): create_auth_request 写入 redirect_origin 字段

为支持 OAuth 回调完成后回跳前端,缓存 auth_request 时一并
保存前端声明的 redirect_origin,跨过 OAuth 跳转后
callback view 仍可读出。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: `_build_login_auth_result_redirect` 重载单元测试 (RED)

**Files:**
- Modify: `server/apps/core/tests/views/test_login_auth_bindings.py` (在 `TestLoginAuthBindingViews` 末尾追加 3 条,覆盖三种条件)

**Interfaces:**
- Consumes: Task 2 的 `validate_redirect_origin`、view 内的 `request`、`urlencode`、`HttpResponseRedirect`。
- Produces: 修改后的签名 `_build_login_auth_result_redirect(request, status_key, message, redirect_origin=None)`。

- [ ] **Step 1: 写 3 条失败测试**

```python
    @patch.dict(os.environ, {}, clear=False)
    def test_build_login_auth_result_redirect_prefers_validated_origin(self):
        from apps.core.views.index_view import _build_login_auth_result_redirect

        os.environ.pop("DEFAULT_ZONE_VAR_NODE_SERVER_URL", None)
        request = RequestFactory().get("/api/v1/core/api/login_auth/callback/")
        request.META["HTTP_X_FORWARDED_HOST"] = "bk.test"
        request.META["HTTP_X_FORWARDED_PROTO"] = "https"

        response = _build_login_auth_result_redirect(
            request,
            "success",
            "认证已完成，可返回原页面继续。",
            redirect_origin="https://bk.test",
        )

        assert response.status_code == 302
        assert response["Location"] == (
            "https://bk.test/auth/signin/login-auth-result?status=success"
            "&message=%E8%AE%A4%E8%AF%81%E5%B7%B2%E5%AE%8C%E6%88%90%EF%BC%8C"
            "%E5%8F%AF%E8%BF%94%E5%9B%9E%E5%8E%9F%E9%A1%B5%E9%9D%A2%E7%BB%A7%E7%BB%AD%E3%80%82"
        )

    @patch.dict(os.environ, {}, clear=False)
    def test_build_login_auth_result_redirect_falls_back_to_relative_when_origin_rejected(self):
        from apps.core.views.index_view import _build_login_auth_result_redirect

        os.environ.pop("DEFAULT_ZONE_VAR_NODE_SERVER_URL", None)
        request = RequestFactory().get("/api/v1/core/api/login_auth/callback/")
        request.META["HTTP_HOST"] = "a.example"

        response = _build_login_auth_result_redirect(
            request,
            "failed",
            "认证失败，请返回原页面重试。",
            redirect_origin="http://b.example",
        )

        # origin 跨 host 被拒,降级到相对路径
        parsed = urlparse(response["Location"])
        assert parsed.scheme == ""
        assert parsed.netloc == ""
        assert parsed.path == "/auth/signin/login-auth-result"

    @patch.dict(os.environ, {}, clear=False)
    def test_build_login_auth_result_redirect_uses_relative_when_origin_missing(self):
        from apps.core.views.index_view import _build_login_auth_result_redirect

        os.environ.pop("DEFAULT_ZONE_VAR_NODE_SERVER_URL", None)
        request = RequestFactory().get("/api/v1/core/api/login_auth/callback/")
        request.META["HTTP_HOST"] = "bk.test"

        # 不传 redirect_origin,沿用相对路径契约(原有行为)
        response = _build_login_auth_result_redirect(
            request,
            "success",
            "认证已完成，可返回原页面继续。",
        )

        parsed = urlparse(response["Location"])
        assert parsed.scheme == ""
        assert parsed.netloc == ""
        assert parsed.path == "/auth/signin/login-auth-result"
```

> 注:第三条的断言含义是「不传 origin 也走得通」,与既有用例 `test_build_login_auth_result_redirect_keeps_relative_path_when_env_configured` 重叠度较高。建议**保留**第三条作为「旧契约不变」的回归保护。

- [ ] **Step 2: 跑测试确认 RED**

```bash
cd /Users/lanyu/Work/bk-lite/server && \
  uv run pytest apps/core/tests/views/test_login_auth_bindings.py \
    -k "build_login_auth_result_redirect_prefers_validated_origin or build_login_auth_result_redirect_falls_back_to_relative or build_login_auth_result_redirect_uses_relative_when_origin_missing" \
    --no-header --no-cov -v 2>&1 | tail -20
```

预期:三条均失败,前两条因缺少 `request` / `redirect_origin` 参数,第三条因签名要求 `request` 不传。

---

### Task 8: `_build_login_auth_result_redirect` 重载实现 (GREEN)

**Files:**
- Modify: `server/apps/core/views/index_view.py`(`_build_login_auth_result_redirect` 函数)

**Interfaces:**
- Produces: 新签名 `_build_login_auth_result_redirect(request, status_key, message, redirect_origin=None)`。

- [ ] **Step 1: 修改函数定义**

把 `server/apps/core/views/index_view.py` 中 `_build_login_auth_result_redirect`(当前签名 `(status_key: str, message: str)`)替换为:

```python
def _build_login_auth_result_redirect(
    request,
    status_key: str,
    message: str,
    redirect_origin: str | None = None,
):
    """生成 OAuth callback 完成后的前端结果页重定向。

    优先级:
      1. 同源校验通过的 redirect_origin → 绝对 URL,跳到前端
      2. 相对路径 /auth/signin/login-auth-result(生产同源部署的兑底)
    """
    query_string = urlencode(
        {
            "status": status_key,
            "message": message,
        }
    )
    path = f"/auth/signin/login-auth-result?{query_string}"
    if redirect_origin and validate_redirect_origin(request, redirect_origin):
        return HttpResponseRedirect(f"{redirect_origin.rstrip('/')}{path}")
    return HttpResponseRedirect(path)
```

并在文件顶部的 `from apps.core.services.login_auth_request_service import (...)` 中追加 `validate_redirect_origin`:

```python
from apps.core.services.login_auth_request_service import (
    build_auth_request_state,
    create_auth_request,
    get_auth_request,
    get_login_auth_callback_uri,
    parse_auth_request_state,
    update_auth_request_status,
    validate_poll_token,
    validate_redirect_origin,   # 新增
)
```

- [ ] **Step 2: 跑既有 8 处的调用点,会发现因参数不匹配而全部失败**

```bash
cd /Users/lanyu/Work/bk-lite/server && \
  uv run pytest apps/core/tests/views/test_login_auth_bindings.py \
    -k "login_auth_callback or build_login_auth_result_redirect_keeps_relative_path" \
    --no-header --no-cov -v 2>&1 | tail -30
```

预期:8 处既有调用点(在 `test_login_auth_callback_*` 用例中)与既有用例 `test_build_login_auth_result_redirect_keeps_relative_path_when_env_configured` 都会因新签名要求 `request` 参数而失败。**这是预期的 RED。** Task 9 将一次性修复 8 处调用点。

- [ ] **Step 3: 不创建 commit**

---

### Task 9: `start_login_auth` 与 `login_auth_callback` 8 处调用点改造

**Files:**
- Modify: `server/apps/core/views/index_view.py`
  - `start_login_auth` 函数:增加 `redirect_origin` 入参解析与透传(1 处)
  - `login_auth_callback` 函数:集中读 `auth_request["redirect_origin"]`,8 处 `_build_login_auth_result_redirect` 调用点同步改(8 处)
- Modify: `server/apps/core/tests/views/test_login_auth_bindings.py`
  - `test_start_login_auth_calls_runtime_and_returns_public_payload`:断言加 `redirect_uri` 与 `redirect_origin` 有关
  - 至少新增 2 条用例(`start_login_auth` 透传 + `login_auth_callback` 集成)

**Interfaces:**
- 消费:`create_auth_request` 现已有 `redirect_origin` 字段;`get_login_auth_callback_uri(request, redirect_origin)`;`validate_redirect_origin`。
- 产出:`start_login_auth` POST 请求体接受可选 `redirect_origin`,`login_auth_callback` 重定向 URL 拼接策略生效。

- [ ] **Step 1: 改造 `start_login_auth` 解析入参**

在 `server/apps/core/views/index_view.py` 的 `start_login_auth` 函数中,找到 `data = _parse_request_data(request)` 之后,追加:

```python
        redirect_origin = (data.get("redirect_origin") or "").strip() or None
```

并修改 `create_auth_request(...)` 调用,在末尾加 `redirect_origin=redirect_origin`:

```python
        auth_request = create_auth_request(
            binding_id=binding.id,
            provider_key=binding.integration_instance.provider_key,
            callback_url=callback_url,
            redirect_origin=redirect_origin,
        )
```

并修改 `redirect_uri=...`,传入 redirect_origin:

```python
            redirect_uri=get_login_auth_callback_uri(request=request, redirect_origin=redirect_origin),
```

- [ ] **Step 2: 改造 `login_auth_callback` 8 处调用点**

把 `server/apps/core/views/index_view.py` 的 `login_auth_callback` 函数,在成功 `auth_request = get_auth_request(auth_request_id)` 之后(但若返回 None 走提前 return 的分支不动),`current_status = auth_request.get("status", "pending")` 之前集中读取:

```python
        # 集中读一次(后续 6 处 status 分支共用);state 解析失败/auth_request 缺失分支
        # 走相对路径,这里 redirect_origin 自然为 None
        redirect_origin = (auth_request or {}).get("redirect_origin") or None
```

然后 **8 处** `_build_login_auth_result_redirect(...)` 调用统一改为:

| 原 | 新 |
|---|---|
| `_build_login_auth_result_redirect("failed", "认证状态无效...")` | `_build_login_auth_result_redirect(request, "failed", "认证状态无效...")` |
| `_build_login_auth_result_redirect("expired", "认证请求已过期...")` | `_build_login_auth_result_redirect(request, "expired", "认证请求已过期...")` |
| `_build_login_auth_result_redirect(current_status, terminal_messages.get(current_status, "..."))` | `_build_login_auth_result_redirect(request, current_status, terminal_messages.get(current_status, "..."), redirect_origin=redirect_origin)` |
| `_build_login_auth_result_redirect("cancelled", "认证已取消...")` *(4 处相似)* | `_build_login_auth_result_redirect(request, "cancelled", "认证已取消...", redirect_origin=redirect_origin)` |
| `_build_login_auth_result_redirect("failed", "认证失败...")` *(多处)* | `_build_login_auth_result_redirect(request, "failed", "认证失败...", redirect_origin=redirect_origin)` |
| `_build_login_auth_result_redirect("success", "认证已完成...")` | `_build_login_auth_result_redirect(request, "success", "认证已完成...", redirect_origin=redirect_origin)` |

> **重要**:前 2 处(state 解析失败 / auth_request 缺失)在拿到 `auth_request` 之前 return,`redirect_origin` 还没声明,直接传 `request` + 不传 `redirect_origin` 即可(走相对路径)。

- [ ] **Step 3: 新增 2 条集成测试**

在 `TestLoginAuthBindingViews` 类末尾追加:

```python
    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "http://10.10.40.91:443"}, clear=False)
    @patch("apps.core.views.index_view.build_login_auth_redirect")
    @patch("apps.core.views.index_view.create_auth_request")
    @patch("apps.core.views.index_view._get_login_auth_binding_by_id")
    def test_start_login_auth_uses_validated_redirect_origin_in_redirect_uri(
        self,
        mock_get_binding,
        mock_create_auth_request,
        mock_build_redirect,
    ):
        from apps.core.views.index_view import start_login_auth

        binding = MagicMock()
        binding.id = 5
        binding.integration_instance.provider_key = "feishu"
        mock_get_binding.return_value = binding
        mock_create_auth_request.return_value = {
            "auth_request_id": "auth-1",
            "poll_token": "poll-1",
            "expires_at": "2026-06-12T10:00:00+00:00",
        }
        mock_build_redirect.return_value = MagicMock(
            success=True,
            payload={"login_url": "https://example.com/sso"},
            summary="",
            to_dict=MagicMock(return_value={"login_url": "https://example.com/sso"}),
        )

        request = RequestFactory().post(
            "/api/v1/core/api/start_login_auth/",
            data=json.dumps({
                "binding_id": 5,
                "callback_url": "/console",
                "redirect_origin": "http://10.10.40.91:443",
            }),
            content_type="application/json",
        )
        # request host 设为同源以通过校验
        request.META["HTTP_HOST"] = "10.10.40.91:443"

        response = start_login_auth(request)

        assert response.status_code == 200
        assert mock_create_auth_request.call_args.kwargs["redirect_origin"] == "http://10.10.40.91:443"
        assert mock_build_redirect.call_args.kwargs["redirect_uri"] == (
            "http://10.10.40.91:443/api/v1/core/api/login_auth/callback/"
        )

    @patch.dict(os.environ, {"DEFAULT_ZONE_VAR_NODE_SERVER_URL": "http://10.10.40.91:443"}, clear=False)
    @patch("apps.core.views.index_view.build_login_auth_redirect")
    @patch("apps.core.views.index_view.create_auth_request")
    @patch("apps.core.views.index_view._get_login_auth_binding_by_id")
    def test_start_login_auth_compatible_without_redirect_origin(
        self,
        mock_get_binding,
        mock_create_auth_request,
        mock_build_redirect,
    ):
        from apps.core.views.index_view import start_login_auth

        binding = MagicMock()
        binding.id = 6
        binding.integration_instance.provider_key = "feishu"
        mock_get_binding.return_value = binding
        mock_create_auth_request.return_value = {
            "auth_request_id": "auth-2",
            "poll_token": "poll-2",
            "expires_at": "2026-06-12T10:00:00+00:00",
        }
        mock_build_redirect.return_value = MagicMock(
            success=True,
            payload={"login_url": "https://example.com/sso"},
            summary="",
            to_dict=MagicMock(return_value={"login_url": "https://example.com/sso"}),
        )

        # 老前端:不传 redirect_origin
        request = RequestFactory().post(
            "/api/v1/core/api/start_login_auth/",
            data=json.dumps({"binding_id": 6, "callback_url": "/console"}),
            content_type="application/json",
        )

        start_login_auth(request)

        # mock_create_auth_request 收到 redirect_origin=None(后端降级到默认空字符串)
        assert mock_create_auth_request.call_args.kwargs["redirect_origin"] in (None, "")
        # redirect_uri 走 env 兑底
        assert mock_build_redirect.call_args.kwargs["redirect_uri"] == (
            "http://10.10.40.91:443/api/v1/core/api/login_auth/callback/"
        )
```

- [ ] **Step 4: 跑全部 login_auth_bindings 测试确认 GREEN**

```bash
cd /Users/lanyu/Work/bk-lite/server && \
  uv run pytest apps/core/tests/views/test_login_auth_bindings.py --no-header --no-cov -q 2>&1 | tail -10
```

预期:全部 PASSED(原有 ~36 条 + 本轮新增 ~14 条 ≈ 50 条)。

- [ ] **Step 5: 跑 system_mgmt 相关测试确认无破坏**

```bash
cd /Users/lanyu/Work/bk-lite/server && \
  uv run pytest apps/system_mgmt/tests/test_integration_instance_serializer.py \
                 apps/system_mgmt/tests/test_integration_instance_viewset.py \
                 apps/system_mgmt/tests/test_runtime_service.py \
                 apps/system_mgmt/tests/test_login_auth_binding_viewset.py \
                 apps/system_mgmt/tests/test_login_auth_manifest.py \
                 apps/system_mgmt/tests/test_builtin_platform_login_auth.py \
    --no-header --no-cov -q 2>&1 | tail -10
```

预期:全部 PASSED(此集合在第一轮已验证过全部 PASSED + 集成详情页的 `IntegrationInstanceSerializer.get_login_auth_callback_url` 不传 `local_port` 后的 `mock_get_login_auth_callback_uri.assert_called_once_with(...)` 调用,需要确认)。

> **关键检查点**:跑完后用 `git diff apps/system_mgmt/tests/test_integration_instance_viewset.py` 看是否动了该文件。如果动过,需要逐条核对。

- [ ] **Step 6: commit**

```bash
cd /Users/lanyu/Work/bk-lite && \
  git add server/apps/core/views/index_view.py \
         server/apps/core/tests/views/test_login_auth_bindings.py && \
  git -c user.name="Claude" -c user.email="noreply@anthropic.com" commit -m "$(cat <<'EOF'
feat(server-core): start_login_auth 接 redirect_origin + callback 8 处统一改造

后端两个面同时启用「前端声明 origin + 后端同源校验」:

- start_login_auth 接收可选 redirect_origin(老前端不传仍兼容),
  透传到 create_auth_request 与 get_login_auth_callback_uri
- login_auth_callback 顶部集中从 cache 读 redirect_origin,
  6 处 status 分支拼绝对 URL,2 处拿到 auth_request 之前的
  失败分支走相对路径兑底

附 2 条集成单测覆盖 start_login_auth 透传与兼容性。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: 前端 `useLoginAuthValidation.ts` 加上 `redirect_origin` 一行

**Files:**
- Modify: `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts:246-249`

**Interfaces:**
- 消费:`window.location.origin`(浏览器 API,权威)。
- 产出:POST body 多一个 `redirect_origin` 字段。

- [ ] **Step 1: 修改 `startLoginAuth` 的 fetch body**

在文件 `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts` 中,找到:

```ts
        body: JSON.stringify({
          binding_id: binding.id,
          callback_url: safeCallbackUrl,
        }),
```

改为:

```ts
        body: JSON.stringify({
          binding_id: binding.id,
          callback_url: safeCallbackUrl,
          redirect_origin: window.location.origin,
        }),
```

- [ ] **Step 2: 跑前端 type-check**

```bash
cd /Users/lanyu/Work/bk-lite/web && pnpm type-check 2>&1 | tail -10
```

预期:无错误(`window.location.origin` 是 TypeScript 标准库定义,无需类型调整)。

- [ ] **Step 3: 跑前端 lint**

```bash
cd /Users/lanyu/Work/bk-lite/web && pnpm lint 2>&1 | tail -10
```

预期:无错误或仅有其它历史文件警告(**本次改动仅一行**,不应引入新 lint 问题)。

- [ ] **Step 4: commit**

```bash
cd /Users/lanyu/Work/bk-lite && \
  git add web/src/app/\(core\)/auth/signin/login-auth/useLoginAuthValidation.ts && \
  git -c user.name="Claude" -c user.email="noreply@anthropic.com" commit -m "$(cat <<'EOF'
feat(web-signin): startLoginAuth 携带 redirect_origin 让后端拼接绝对 URL

浏览器侧的 window.location.origin 是当前页 origin 的权威,
后端配合 validate_redirect_origin 同源校验接收。

与后端 Task 1-9 同步发布即可端到端打通 OAuth 回调。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

> 注:路径中的括号需要 shell 转义(已在上面命令中处理)。

---

### Task 11: 全量验证与冒烟

**Files:**
- (无代码改动,纯验证)

- [ ] **Step 1: 后端全量测试**

```bash
cd /Users/lanyu/Work/bk-lite/server && make test 2>&1 | tail -30
```

预期:全部 PASSED。如果有 collection error 是预存问题(`apps.core.logger` 找不到 `system_mgmt_logger`),与本次无关——已在前几轮确认 stash 后仍存在。

如果发现新的失败:
- 若涉及 `test_integration_instance_viewset.py` 的 `mock_get_login_auth_callback_uri.assert_called_once_with(...)`:检查 mock 的 `side_effect` 是否断言了 `redirect_origin=None`。若是,需要更新 mock 的 `assert_called_once_with` 形参,或在 mock 上设置 `return_value` 不依赖特定传参(参考 Task 9 Step 5 验证)。

- [ ] **Step 2: 后端覆盖检查**

```bash
cd /Users/lanyu/Work/bk-lite/server && \
  uv run pytest apps/core/tests/views/test_login_auth_bindings.py \
    --cov=apps.core.services.login_auth_request_service \
    --cov=apps.core.views.index_view \
    --cov-report=term-missing -q 2>&1 | grep -E "login_auth_request_service|index_view.py"
```

预期:
- `login_auth_request_service.py`:覆盖率 ≥ 75%(整体);新函数 `validate_redirect_origin` 与 `get_login_auth_callback_uri` 新分支 100%
- `index_view.py`:覆盖率不降低

- [ ] **Step 3: 前端全量验证**

```bash
cd /Users/lanyu/Work/bk-lite/web && pnpm type-check && pnpm lint 2>&1 | tail -15
```

预期:无错误。

- [ ] **Step 4: 确认未改 env 文件**

```bash
cd /Users/lanyu/Work/bk-lite && git diff server/.env server/envs/.env.node.example
```

预期:无输出。

- [ ] **Step 5: 端到端冒烟(可选,需要本地 dev)**

1. 启动后端:`cd server && make dev`(或 `uvicorn asgi:application --host 0.0.0.0 --port 8001`)
2. 启动前端:`cd web && pnpm dev`(默认 3000)
3. 浏览器:进入 `http://localhost:3000/auth/signin`,点飞书登录
4. 观察:DevTools → Network → start_login_auth 请求,body 含 `redirect_origin: "http://localhost:3000"`
5. 飞书授权完成回调,应落在 `http://localhost:3000/auth/signin/login-auth-result?status=success&...`(若反代设置了 X-Forwarded-Host),或相对路径(若未设置)

**不在本任务范围做冒烟验证**——若有本地反代配置则推荐跑;若无,只跑 Step 1-4 的回归即可。

---

## Self-Review 自检(plan 内联)

按 writing-plans skill 的 self-review 清单核对:

**1. Spec coverage:**

| Spec 章节 | 对应 Plan Task |
|---|---|
| §1.3 G1 (callback URL + 回跳 都支持 redirect_origin) | Task 4 + Task 8(双 URL 函数都升级) |
| §1.3 G2 (严格同源校验) | Task 2(纯函数) + Task 1(9 条用例) |
| §1.3 G3 (降级路径保留) | Task 4 + Task 8(均做 `if 校验 → else 兜底`) |
| §1.3 G4 (配置只减不增) | 全 plan 无新增 env |
| §1.3 G5 (新代码 100% 覆盖) | Task 1 + Task 3 + Task 5 + Task 7 + Task 9 全部先 RED |
| §1.3 G6 (前后端可分开升级) | `redirect_origin` 是可选,旧前端不传仍工作(Task 9 兼容性用例) |
| §2.1 `validate_redirect_origin` | Task 2 |
| §2.2 `get_login_auth_callback_uri` 重载 | Task 4 |
| §2.3 `create_auth_request` 加字段 | Task 6 |
| §2.4 `_build_login_auth_result_redirect` 重载 | Task 8 |
| §2.5 `start_login_auth` 改造 | Task 9 Step 1 |
| §2.6 `login_auth_callback` 8 处改造 | Task 9 Step 2 |
| §2.7 前端 1 行 | Task 10 |
| §5.1 21 条用例 | Task 1(9) + Task 3(3) + Task 5(1) + Task 7(3) + Task 9(2 + 既有 ~3) ≈ 21 |
| §6 文件改动清单 | 全部覆盖 |

✅ 无遗漏。

**2. 占位符扫描:**

无 TBD/TODO/FIXME/XXX/"similar to"。所有代码块都是完整可执行内容。✅

**3. 类型一致性:**

- `validate_redirect_origin(request, redirect_origin) -> bool`:Task 1 定义,Task 2 实现,Task 3/8/9 调用,**一致**。
- `get_login_auth_callback_uri(request=None, redirect_origin=None) -> str`:Task 3 定义,Task 4 实现,Task 9 调用,**一致**。
- `create_auth_request(binding_id, provider_key, callback_url, redirect_origin=None) -> dict`:Task 5 定义,Task 6 实现,Task 9 调用,**一致**。
- `_build_login_auth_result_redirect(request, status_key, message, redirect_origin=None)`:Task 7 定义,Task 8 实现,Task 9 调用,**一致**。
- `auth_request["redirect_origin"]`:Task 6 存储,Task 9 读取,**一致**。

✅ 一致。

**4. 实施顺序符合 TDD:** 每个 Task 都是「先写失败测试 → 实现 → 验证 GREEN」,Task 8 后有一个"既有 8 处会失败"的红阶段属于预期(TDD 强调先红后绿)。Task 9 是规模性修复,在 Step 4 一次性回归。

---

**Plan 总耗时预估**:11 个任务,每个 2-5 分钟步骤,合计约 4-6 小时有效工程时间。代码 ~60 行 + 测试 ~260 行 + 文档已就位。
