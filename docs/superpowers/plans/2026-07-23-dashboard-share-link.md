# 运营分析画布永久分享链接差异实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留现有分享登录、Token 兑换、账号隔离、只读画布和受限数据查询能力的前提下，删除链接过期与主动撤销功能，并把现有短会话调整为固定 8 小时、按访问者复用。

**Architecture:** 不重建分享功能，也不重构已工作的查询和权限链路。只沿现有 `DashboardShareLink → token exchange → DashboardShareSession → share_view` 流程修改生命周期数据与入口契约；每个删除步骤都由现有安全行为回归测试保护。

**Tech Stack:** Django、Django REST Framework、Django ORM、pytest、Next.js 16、React 19、TypeScript、Ant Design。

## Global Constraints

- 实施依据：`docs/superpowers/specs/2026-07-23-dashboard-share-link-design.md`。
- 这是对现有功能的差异修改，不重新创建已有模块、页面、路由、权限解析或数据源查询链路。
- 链接永久有效，不支持有效期、续期、主动撤销或单链接 Token 轮换。
- 同一“画布实例 + 分享者账号及身份域”重复创建返回同一链接。
- 短会话固定有效 `28800` 秒；普通请求不续期，重新打开原始链接时重置 8 小时。
- 同一“链接 + 实际访问者账号及身份域”复用未过期 session；过期时删除旧 session 并创建新 session。
- 只有分享请求实际观测到分享者失权时，链接才永久失效。
- 保留现有跨租户登录访问、sessionId 账号绑定、单画布隔离、数据源白名单、敏感字段过滤、只读查询和前端只读模式。
- 保留现有画布删除和跨空间/租户变化导致链接永久失效的行为。
- 同一空间内仅移动目录不得导致链接失效。
- 访问者仍然不能编辑、保存、删除、复制、迁移或导出。
- `0017_dashboard_share_link.py` 只存在于本地且未共享，允许清空本地分享数据并直接重写。
- 不修改与本次生命周期调整无关的普通画布接口、普通权限缓存和数据源实现。
- 不执行 `git add` 或 `git commit`，由用户自行提交。

---

## 当前基线与差异

### 必须保留，不重新实现

| 现有能力 | 主要位置 | 保护方式 |
|---|---|---|
| 原始 Token 登录后兑换短会话 | `share/[token]/page.tsx`、`share_view.py` | 保留路由和兑换接口，运行跨租户兑换测试 |
| 登录后 URL 不保留原始 Token | `share/[token]/page.tsx` | 保留 `router.replace(session URL)` |
| sessionId 绑定访问者账号 | `share_service.resolve_session()` | 保留账号和身份域比较测试 |
| 分享者权限实时校验 | `share_service.resolve_link()` | 只删除权限版本依赖，不删除 `can_view_dashboard()` |
| 单画布和数据源范围隔离 | `share_view.py` | 不重构，运行未引用数据源 403 测试 |
| 分享者运行时数据权限 | `share_view.py` 现有查询路径 | 运行真实引用数据源查询测试 |
| 数据源敏感字段过滤 | `share_view.py` | 运行 metadata secret-free 测试 |
| 分享页面只读模式 | `Dashboard shareMode` | 不修改 Dashboard 查询适配，仅精简分享弹窗 |
| `/ops-analysis/share/` 菜单守卫放行 | `web/src/app/layout.tsx` | 不回退现有修复，纳入静态或浏览器回归 |
| 分享页不请求 namespace | 分享数据源 context | 不改普通 namespace API，浏览器监听验证 |
| 分享页面高度与 overflow 修复 | 分享 session 页面容器 | 不改布局结构，浏览器截图验证无外层滚动 |

### 本次必须删除

- 链接字段：`expires_at`、`token_version`、`authorization_version`。
- 链接状态：`expired`、`revoked`。
- session 字段：`revoked_at`。
- 服务逻辑：有效期解析、过期标记、续期更新、主动撤销、撤销 session。
- 管理接口：GET 分享列表、DELETE 撤销链接。
- 前端逻辑：永久/限时选择、天数输入、链接列表、过期时间、撤销按钮。
- 前端 API：`listShares()`、`revokeShare()` 及创建接口中的有效期参数。

### 本次必须修改

- Token 从 `public_id + token_version + signature` 改为固定协议版本字节、`public_id + signature`。
- 创建服务从 `create_or_update_share(...)` 收敛为无有效期参数的幂等创建/获取。
- `exchange_share()` 从每次创建 session 改为同账号复用。
- 默认短会话由 1800 秒改为 28800 秒。
- 画布变更信号不再把同空间目录移动视作分享失效。
- 失效提示删除“过期、撤销”文案。

---

### Task 1: 先锁定现有安全基线

**Files:**
- Modify: `server/apps/operation_analysis/tests/test_share_service.py`
- Modify: `server/apps/operation_analysis/tests/test_share_api.py`
- Modify: `web/scripts/ops-analysis-dashboard-share-test.ts`

**Purpose:** 在删除代码前，把不能被打坏的现有行为固化成回归测试。本任务不修改产品代码。

**Interfaces:**
- Consumes current `create_or_update_share()`、`exchange_share()`、`resolve_session()`。
- Produces regression gates used by Tasks 2–4。

- [ ] **Step 1: 保留并确认后端现有安全测试**

`test_share_api.py` 中以下测试必须保留，不因生命周期变化删除：

```python
test_cross_tenant_visitor_can_exchange_and_read_dashboard
test_share_query_rejects_datasource_not_declared_by_dashboard
test_share_datasource_metadata_is_scoped_and_secret_free
test_share_query_uses_sharer_runtime_authorization_context
```

`test_share_service.py` 中以下语义必须保留：

```python
test_share_session_is_bound_to_visitor
test_dashboard_delete_permanently_invalidates_link
test_dashboard_move_permanently_invalidates_link
test_routine_permission_cache_clear_does_not_invalidate_link
test_actual_permission_loss_permanently_invalidates_link_and_session
```

- [ ] **Step 2: 增加跨账号 session 反向拒绝测试**

```python
@pytest.mark.django_db
def test_share_sessions_cannot_be_used_across_visitors(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_update_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
        permanent=True,
    )
    visitor_c = User.objects.create(
        username="carol",
        domain="third.com",
        display_name="Carol",
        email="carol@example.com",
        password="x",
    )
    session_b = exchange_share(token=result.token, visitor=visitor)
    session_c = exchange_share(token=result.token, visitor=visitor_c)

    with pytest.raises(ShareLinkInvalid):
        resolve_session(session_id=session_b.session_id, visitor=visitor_c)
    with pytest.raises(ShareLinkInvalid):
        resolve_session(session_id=session_c.session_id, visitor=visitor)
```

- [ ] **Step 3: 增加普通分享请求不得续期 session 的测试**

```python
@pytest.mark.django_db
def test_resolve_session_does_not_extend_expiry(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_update_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
        permanent=True,
    )
    session = exchange_share(token=result.token, visitor=visitor)
    original_expiry = session.expires_at

    resolve_session(session_id=session.session_id, visitor=visitor)

    session.refresh_from_db()
    assert session.expires_at == original_expiry
```

- [ ] **Step 4: 给前端静态测试补充现有修复保护**

```typescript
assert.match(layoutSource, /pathname\.startsWith\('\/ops-analysis\/share\/'\)/);
assert.match(sharePageSource, /overflow-hidden/);
assert.doesNotMatch(sharePageSource, /namespace/);
```

如果当前脚本使用不同变量名，沿用脚本现有的文件读取方式，只添加等价断言，不改产品代码。

- [ ] **Step 5: 运行基线**

Run:

```powershell
cd server
uv run pytest `
  apps/operation_analysis/tests/test_share_service.py `
  apps/operation_analysis/tests/test_share_api.py -q
cd ../web
pnpm test:ops-analysis-dashboard-share
```

Expected: 现有测试和新增保护测试 PASS。若新增测试暴露当前缺陷，先记录为基线缺陷；不要在后续删除生命周期代码时绕过断言。

---

### Task 2: 最小化修改数据结构和 Token

**Files:**
- Modify: `server/apps/operation_analysis/models/share_models.py`
- Modify: `server/apps/operation_analysis/migrations/0017_dashboard_share_link.py`
- Modify: `server/apps/operation_analysis/services/share_token.py`
- Modify: `server/apps/operation_analysis/tests/test_share_models.py`
- Modify: `server/apps/operation_analysis/tests/test_share_token.py`

**Purpose:** 只删除生命周期不再需要的字段，不改变画布、分享者、访问者和资源绑定字段。

**Interfaces:**
- Produces: `DashboardShareLink.Status.ACTIVE | SHARER_PERMISSION_LOST | DASHBOARD_INVALID`
- Produces: `DashboardShareLink.is_usable() -> bool`
- Produces: `build_share_token(public_id: UUID) -> str`
- Produces: `parse_share_token(token: str) -> UUID`
- Preserves: `mark_invalid(reason, actor)`、分享者/画布绑定字段、审计失效字段。

- [ ] **Step 1: 先将模型测试改成目标差异**

```python
@pytest.mark.django_db
def test_share_link_contains_no_expiry_revocation_or_version_fields(dashboard):
    link = DashboardShareLink.objects.create(
        dashboard=dashboard,
        dashboard_instance_id=dashboard.pk,
        tenant_domain=dashboard.domain,
        space_id=1,
        sharer_username="alice",
        sharer_domain="domain.com",
    )
    fields = {field.name for field in link._meta.fields}
    assert "expires_at" not in fields
    assert "token_version" not in fields
    assert "authorization_version" not in fields
    assert set(DashboardShareLink.Status.values) == {
        "active",
        "sharer_permission_lost",
        "dashboard_invalid",
    }


@pytest.mark.django_db
def test_session_is_unique_for_link_and_visitor(share_link):
    values = {
        "share_link": share_link,
        "visitor_username": "bob",
        "visitor_domain": "other.com",
        "expires_at": timezone.now() + timedelta(hours=8),
    }
    DashboardShareSession.objects.create(**values)
    with pytest.raises(IntegrityError):
        DashboardShareSession.objects.create(**values)
```

- [ ] **Step 2: 运行模型测试，确认旧字段导致失败**

Run:

```powershell
cd server
uv run pytest apps/operation_analysis/tests/test_share_models.py -q
```

Expected: FAIL，旧模型仍有过期、撤销和版本字段。

- [ ] **Step 3: 对现有模型做字段级删减**

在 `DashboardShareLink` 中：

```python
class Status(models.TextChoices):
    ACTIVE = "active", "有效"
    SHARER_PERMISSION_LOST = "sharer_permission_lost", "分享者失权"
    DASHBOARD_INVALID = "dashboard_invalid", "画布失效"


def is_usable(self):
    return self.status == self.Status.ACTIVE
```

删除：

```python
token_version
authorization_version
expires_at
Status.EXPIRED
Status.REVOKED
models.Index(fields=["status", "expires_at"], ...)
```

在 `DashboardShareSession` 中删除 `revoked_at`，增加：

```python
refreshed_at = models.DateTimeField(auto_now=True)

class Meta:
    db_table = "operation_analysis_dashboard_share_session"
    constraints = [
        models.UniqueConstraint(
            fields=["share_link", "visitor_username", "visitor_domain"],
            name="uniq_share_session_by_visitor",
        )
    ]
```

不要删除 `tenant_domain`、`space_id`、`dashboard_instance_id`、分享者字段、访问者字段、`invalidated_at`、`invalidated_by` 或 `invalidation_reason`。

- [ ] **Step 4: 重写未共享的 `0017`**

使 `0017_dashboard_share_link.py` 直接创建上述最终结构。不要增加 `0018`，也不要编写旧数据转换逻辑。迁移中保留：

- 活动链接条件唯一约束；
- `public_id` 唯一约束；
- link/session 外键；
- link/visitor 会话唯一约束；
- 画布、租户和空间查询所需索引。

- [ ] **Step 5: 先修改 Token 测试**

```python
def test_share_token_round_trip_without_row_version(settings):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    public_id = uuid.uuid4()
    assert parse_share_token(build_share_token(public_id)) == public_id


def test_share_token_rejects_tampering(settings):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    token = build_share_token(uuid.uuid4())
    replacement = "A" if token[-1] != "A" else "B"
    with pytest.raises(InvalidShareToken):
        parse_share_token(token[:-1] + replacement)
```

- [ ] **Step 6: 最小修改 Token payload**

保留现有 Base64URL、HMAC、密钥读取和常量时间比较实现，只把 payload 改为：

```python
PROTOCOL_VERSION = b"\x01"
PAYLOAD_SIZE = 17
SIGNATURE_SIZE = 32


def build_share_token(public_id):
    payload = PROTOCOL_VERSION + public_id.bytes
    signature = hmac.digest(_signing_key(), payload, "sha256")
    return base64.urlsafe_b64encode(payload + signature).rstrip(b"=").decode("ascii")


def parse_share_token(token):
    raw = _decode_base64url(token)
    if len(raw) != PAYLOAD_SIZE + SIGNATURE_SIZE:
        raise InvalidShareToken
    payload, supplied = raw[:PAYLOAD_SIZE], raw[PAYLOAD_SIZE:]
    if payload[:1] != PROTOCOL_VERSION:
        raise InvalidShareToken
    expected = hmac.digest(_signing_key(), payload, "sha256")
    if not hmac.compare_digest(supplied, expected):
        raise InvalidShareToken
    return uuid.UUID(bytes=payload[1:])
```

- [ ] **Step 7: 重新应用本地迁移并执行本任务回归**

Run:

```powershell
cd server
uv run python manage.py migrate operation_analysis 0016
uv run python manage.py migrate operation_analysis 0017
uv run python manage.py makemigrations --check --dry-run
uv run pytest `
  apps/operation_analysis/tests/test_share_models.py `
  apps/operation_analysis/tests/test_share_token.py -q
```

Expected: 分享数据表重建成功；`No changes detected`；模型与 Token 测试 PASS。

---

### Task 3: 在现有服务上替换生命周期，不动查询链路

**Files:**
- Modify: `server/apps/operation_analysis/services/share_service.py`
- Modify: `server/apps/operation_analysis/serializers/share_serializers.py`
- Modify: `server/apps/operation_analysis/views/view.py`
- Modify: `server/apps/operation_analysis/signals.py`
- Modify: `server/config/components/base.py`
- Modify: `server/envs/.env.example`
- Modify: `server/apps/operation_analysis/tests/test_share_service.py`
- Modify: `server/apps/operation_analysis/tests/test_share_api.py`

**Purpose:** 删除链接有效期和撤销分支，并将现有 session 创建改为复用；不修改 `share_view.py` 的画布详情、数据源过滤和查询实现。

**Interfaces:**
- Rename: `create_or_update_share(...)` → `create_or_get_share(*, dashboard, sharer, tenant_domain, space_id)`
- Preserve: `resolve_link(link) -> SharePrincipal`
- Preserve: `exchange_share(*, token, visitor) -> DashboardShareSession`
- Preserve: `resolve_session(*, session_id, visitor) -> SharePrincipal`
- Delete: `ShareDurationInvalid`、`_resolve_expiry()`、`revoke_share()`。

- [ ] **Step 1: 把生命周期测试改为目标行为**

删除只验证以下旧能力的测试：

```python
test_expired_link_is_not_reactivated
test_duration_is_bounded
test_revocation_invalidates_existing_session
```

将重复创建测试改为：

```python
@pytest.mark.django_db
def test_create_returns_same_permanent_token(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    first = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    second = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    assert second.link.pk == first.link.pk
    assert second.token == first.token
    assert DashboardShareLink.objects.filter(
        dashboard_instance_id=dashboard.pk,
        sharer_username=sharer.username,
        sharer_domain=sharer.domain,
        status=DashboardShareLink.Status.ACTIVE,
    ).count() == 1
```

- [ ] **Step 2: 增加短会话复用测试**

```python
@pytest.mark.django_db
def test_exchange_reuses_unexpired_session_and_resets_eight_hours(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    settings.DASHBOARD_SHARE_SESSION_AGE = 28800
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    first = exchange_share(token=result.token, visitor=visitor)
    exchange_time = first.expires_at - timedelta(hours=1)

    with mock.patch(
        "apps.operation_analysis.services.share_service.timezone.now",
        return_value=exchange_time,
    ):
        second = exchange_share(token=result.token, visitor=visitor)

    assert second.session_id == first.session_id
    assert second.expires_at == exchange_time + timedelta(hours=8)


@pytest.mark.django_db
def test_exchange_replaces_expired_session(
    settings, share_result, visitor
):
    first = exchange_share(token=share_result.token, visitor=visitor)
    DashboardShareSession.objects.filter(pk=first.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    second = exchange_share(token=share_result.token, visitor=visitor)
    assert second.session_id != first.session_id
    assert not DashboardShareSession.objects.filter(pk=first.pk).exists()
```

- [ ] **Step 3: 增加弱化失权语义测试**

```python
@pytest.mark.django_db
def test_permission_loss_becomes_permanent_only_when_observed(
    settings, dashboard, sharer, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )

    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: False,
    )
    with pytest.raises(ShareLinkInvalid):
        resolve_link(result.link)

    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.SHARER_PERMISSION_LOST
    with pytest.raises(ShareLinkInvalid):
        resolve_link(result.link)
```

不再模拟权限缓存版本，也不修改 `permission_cache.py`。

- [ ] **Step 4: 最小替换创建服务**

保留现有 `can_view_dashboard()` 和 `SharePrincipal`，将创建函数改为：

```python
@transaction.atomic
def create_or_get_share(*, dashboard, sharer, tenant_domain, space_id):
    if not can_view_dashboard(user=sharer, dashboard=dashboard, space_id=space_id):
        raise SharePermissionDenied
    link = (
        DashboardShareLink.objects.select_for_update()
        .filter(
            dashboard_instance_id=dashboard.pk,
            sharer_username=sharer.username,
            sharer_domain=sharer.domain,
            status=DashboardShareLink.Status.ACTIVE,
        )
        .first()
    )
    if link is None:
        link = DashboardShareLink.objects.create(
            dashboard=dashboard,
            dashboard_instance_id=dashboard.pk,
            tenant_domain=tenant_domain,
            space_id=space_id,
            sharer_username=sharer.username,
            sharer_domain=sharer.domain,
        )
    return ShareLinkResult(link=link, token=build_share_token(link.public_id))
```

删除时长常量、时长异常、过期检查和撤销函数。`_resolve_link_from_token()` 改为：

```python
def _resolve_link_from_token(token):
    try:
        public_id = parse_share_token(token)
        link = DashboardShareLink.objects.select_related("dashboard").get(
            public_id=public_id,
        )
    except (InvalidShareToken, DashboardShareLink.DoesNotExist) as exc:
        raise ShareLinkInvalid from exc
    if not link.is_usable():
        raise ShareLinkInvalid
    return link
```

不要改动 `resolve_link()` 中分享者账号、画布查看权限、画布实例和租户归属校验。

- [ ] **Step 5: 在现有 `exchange_share()` 中加入复用**

```python
@transaction.atomic
def exchange_share(*, token, visitor):
    link = _resolve_link_from_token(token)
    resolve_link(link)
    now = timezone.now()
    expires_at = now + timedelta(seconds=settings.DASHBOARD_SHARE_SESSION_AGE)
    session = (
        DashboardShareSession.objects.select_for_update()
        .filter(
            share_link=link,
            visitor_username=visitor.username,
            visitor_domain=visitor.domain,
        )
        .first()
    )
    if session is not None and session.expires_at <= now:
        session.delete()
        session = None
    if session is None:
        return DashboardShareSession.objects.create(
            share_link=link,
            visitor_username=visitor.username,
            visitor_domain=visitor.domain,
            expires_at=expires_at,
        )
    session.expires_at = expires_at
    session.save(update_fields=["expires_at", "refreshed_at"])
    return session
```

在 `resolve_session()` 中仅删除 `revoked_at` 判断，保留：

```python
session.expires_at <= timezone.now()
session.visitor_username != visitor.username
session.visitor_domain != visitor.domain
return resolve_link(session.share_link)
```

普通请求不得保存或更新 session。

- [ ] **Step 6: 删除旧管理接口，不碰分享数据接口**

在 `share_serializers.py` 删除 `ShareCreateSerializer`，保留 `ShareExchangeSerializer`。

在 `DashboardModelViewSet`：

- `share` action 从 `methods=["get", "post"]` 改为 `methods=["post"]`；
- 删除 GET 列表分支；
- 删除 `revoke_share_link` action；
- 删除旧参数解析和 `ShareDurationInvalid`；
- 返回字段收敛为 `id`、`url`、`status`、`sharer_username`。

```python
@HasPermission("view-View")
@action(detail=True, methods=["post"], url_path="share")
def share(self, request, *args, **kwargs):
    dashboard = self.get_object()
    try:
        result = create_or_get_share(
            dashboard=dashboard,
            sharer=request.user,
            tenant_domain=dashboard.domain,
            space_id=self._parse_current_team_cookie(request),
        )
    except SharePermissionDenied as exc:
        raise PermissionDenied("无权分享该仪表盘") from exc
    response = Response({
        "id": result.link.id,
        "url": f"/ops-analysis/share/{result.token}",
        "status": result.link.status,
        "sharer_username": result.link.sharer_username,
    })
    log_ops_analysis_success(
        request,
        response,
        "create",
        f"获取仪表盘分享链接: {dashboard.name}",
    )
    return response
```

不要修改 `share_view.py` 的 detail、query、data_sources action 或其响应字段过滤。

- [ ] **Step 7: 收窄画布信号**

保留删除时主动失效。`pre_save` 只比较真正改变空间或租户身份的字段：

```python
if previous["groups"] != instance.groups or previous["domain"] != instance.domain:
    _invalidate_dashboard_links(instance.pk)
```

删除 `directory_id` 比较，避免同空间目录移动误伤链接。

- [ ] **Step 8: 更新配置**

`server/config/components/base.py`：

```python
DASHBOARD_SHARE_SESSION_AGE = int(
    os.getenv("DASHBOARD_SHARE_SESSION_AGE", "28800")
)
```

`server/envs/.env.example`：

```dotenv
# 固定的分享签名密钥；轮换会使全部已有分享链接失效
DASHBOARD_SHARE_SIGNING_KEY=
# 分享短会话有效期（秒）；普通请求不续期，默认 8 小时
DASHBOARD_SHARE_SESSION_AGE=28800
```

- [ ] **Step 9: 更新 API 测试为 POST-only**

用下列测试替换旧 `test_create_and_revoke_share_api`：

```python
@pytest.mark.django_db
def test_share_api_is_idempotent_and_post_only(
    settings, dashboard, sharer, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    client = APIClient()
    client.force_authenticate(sharer)
    client.cookies["current_team"] = "1"
    path = f"/api/v1/operation_analysis/api/dashboard/{dashboard.id}/share/"

    first = client.post(path, {}, format="json")
    second = client.post(path, {}, format="json")

    assert first.status_code == second.status_code == 200
    assert first.data["url"] == second.data["url"]
    assert set(first.data) == {"id", "url", "status", "sharer_username"}
    assert client.get(path).status_code == 405
    assert client.delete(f"{path}{first.data['id']}/").status_code == 404
```

其余安全测试只把创建请求体从 `{"permanent": True}` 改为 `{}`，不改变其断言。

- [ ] **Step 10: 运行后端差异回归**

Run:

```powershell
cd server
uv run pytest `
  apps/operation_analysis/tests/test_share_models.py `
  apps/operation_analysis/tests/test_share_token.py `
  apps/operation_analysis/tests/test_share_service.py `
  apps/operation_analysis/tests/test_share_api.py -q
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
```

Expected: 全部 PASS；无待生成迁移；分享数据源和查询测试仍通过。

---

### Task 4: 只精简前端管理 UI，保留分享查看页

**Files:**
- Modify: `web/src/app/ops-analysis/api/dashboardShare.ts`
- Modify: `web/src/app/ops-analysis/types/dashboardShare.ts`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/shareDialog.tsx`
- Modify: `web/src/app/ops-analysis/share/[token]/page.tsx`
- Modify: `web/src/app/ops-analysis/share/session/[sessionId]/shareDashboardPage.tsx`
- Modify: `web/scripts/ops-analysis-dashboard-share-test.ts`

**Purpose:** 删除分享管理 UI 的旧功能，不改现有 Token 页、session 页、Dashboard `shareMode` 和分享数据源 context 的结构。

**Interfaces:**
- Rename: `createOrUpdateShare(dashboardId, data)` → `createShare(dashboardId)`
- Delete: `listShares()`、`revokeShare()`
- Preserve: `exchangeShare()`、`getSharedDashboard()`、`querySharedDataSource()`、`getSharedDataSources()`

- [ ] **Step 1: 先更新前端静态契约**

```typescript
assert.match(apiSource, /const createShare = useCallback/);
assert.doesNotMatch(apiSource, /listShares|revokeShare|duration_seconds|permanent/);
assert.match(dialogSource, /复制分享链接/);
assert.doesNotMatch(dialogSource, /限时有效|永久有效|InputNumber|Radio|撤销/);
assert.match(tokenPageSource, /router\.replace\(`\/ops-analysis\/share\/session\//);
assert.doesNotMatch(tokenPageSource, /已被撤销|过期/);
assert.match(layoutSource, /pathname\.startsWith\('\/ops-analysis\/share\/'\)/);
```

- [ ] **Step 2: 最小修改 API hook**

保留现有兑换、详情、查询和数据源函数，只替换管理部分：

```typescript
const createShare = useCallback(
  (dashboardId: string | number) =>
    post(`/operation_analysis/api/dashboard/${dashboardId}/share/`, {}),
  [post],
);
```

返回对象中删除 `createOrUpdateShare`、`listShares` 和 `revokeShare`，增加 `createShare`。如果 `del` 不再被其他函数使用，从 `useApiClient()` 解构中删除 `del`；保留 `get` 和 `post`。

- [ ] **Step 3: 收敛响应类型**

```typescript
export interface DashboardShareLinkDto {
  id: number;
  url: string;
  status: 'active' | 'sharer_permission_lost' | 'dashboard_invalid';
  sharer_username: string;
}
```

不要修改 `SharedDashboardDto`。

- [ ] **Step 4: 将现有弹窗改成单按钮**

```tsx
'use client';

import React, { useState } from 'react';
import { Button, Modal, Typography, message } from 'antd';
import { useDashboardShareApi } from '@/app/ops-analysis/api/dashboardShare';

interface ShareDialogProps {
  dashboardId: string | number;
  open: boolean;
  onClose: () => void;
}

const ShareDialog: React.FC<ShareDialogProps> = ({
  dashboardId,
  open,
  onClose,
}) => {
  const { createShare } = useDashboardShareApi();
  const [loading, setLoading] = useState(false);

  const copyShareLink = async () => {
    setLoading(true);
    try {
      const link = await createShare(dashboardId);
      await navigator.clipboard.writeText(
        `${window.location.origin}${link.url}`,
      );
      message.success('分享链接已复制');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title="分享仪表盘"
      open={open}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        任何已登录用户获得链接后，都可以按你的当前权限查看该画布。
      </Typography.Paragraph>
      <Button type="primary" loading={loading} onClick={copyShareLink}>
        复制分享链接
      </Button>
    </Modal>
  );
};

export default ShareDialog;
```

- [ ] **Step 5: 只更新失效文案**

Token 页和 session 页统一保留标题：

```tsx
<h2>分享链接无效或已失效</h2>
```

Token 页正文：

```tsx
<p>该分享链接当前不可用，或你没有访问权限。</p>
```

Session 页正文：

```tsx
<p>当前分享会话不可用，请重新打开原始分享链接。</p>
```

不要修改：

- 未登录时 `signIn(...callbackUrl...)`；
- 登录后 `exchangeShare(params.token)`；
- `router.replace('/ops-analysis/share/session/...')`；
- `ShareDataSourceProvider`；
- `OpsAnalysisProvider`；
- Dashboard 的 `shareMode`、`shareSessionId` 和详情 override；
- session 页面 `metadata.referrer = 'no-referrer'`；
- 分享页现有高度和 overflow 修复。

- [ ] **Step 6: 运行前端回归**

Run:

```powershell
cd web
pnpm test:ops-analysis-dashboard-share
pnpm lint
pnpm typecheck
```

Expected: 全部 PASS；没有旧有效期、列表或撤销引用；分享查看链路类型检查不受影响。

---

### Task 5: 定向浏览器验收与清理

**Files:**
- Create: `test-results/dashboard-share-permanent-link/README.md`

**Purpose:** 只验证本次差异和最容易受影响的既有链路，不重复执行整套从零功能验收。

- [ ] **Step 1: 验收管理 UI 和幂等创建**

使用账号 A：

1. 打开已有测试画布；
2. 分享弹窗只显示“复制分享链接”；
3. 连续复制两次；
4. 记录脱敏 Token，确认两次 Token 相同；
5. 确认创建接口均为 POST 200；
6. 确认没有 GET 分享列表和 DELETE 撤销请求。

- [ ] **Step 2: 验收原始链接与短会话**

使用 Anonymous、B、C 三个独立 BrowserContext：

1. Anonymous 打开原始链接后进入登录；
2. B 登录后回到分享目标并跳转短会话 URL；
3. 地址栏不再包含原始 Token；
4. C 打开同一原始链接获得不同 sessionId；
5. B/C 互用对方 sessionId 均被拒绝；
6. B 再次打开原始链接，复用自己的 sessionId；
7. 从接口或数据库确认 B 的 `expires_at` 被重置为约 8 小时后；
8. 普通刷新和查询不改变 `expires_at`。

- [ ] **Step 3: 验收未被打坏的分享查看能力**

在 B 的分享页确认：

- 画布与图表正常显示；
- 刷新、筛选和图表查询正常；
- 真实引用数据源请求成功；
- 未引用数据源请求返回 403；
- 没有编辑、删除、复制、迁移和导出入口；
- 直接调用写接口被后端拒绝；
- 不请求 `/api/namespace?ids=...`；
- 页面外层没有多余滚动条；
- 响应不包含连接配置、数据库账号、密码、Token、Secret 或连接字符串。

- [ ] **Step 4: 验收请求观测失权**

1. 保持 B 页面打开；
2. 撤销 A 对测试画布的查看权限；
3. 由 B 刷新或发起查询，使服务端实际观测失权；
4. 恢复 A 权限；
5. 确认旧原始链接和 B/C 旧 session 均持续无效；
6. A 再次创建得到新 Token。

不在浏览器中把“撤权后未发生任何分享请求，随后恢复权限”判为缺陷；该弱化语义由后端测试明确覆盖。

- [ ] **Step 5: 验收画布生命周期差异**

- 同空间移动目录：旧链接继续有效；
- 复制画布：副本不继承分享关系；
- 删除测试画布：旧链接和 session 失效；
- 跨空间迁移独立测试画布：旧链接失效。

- [ ] **Step 6: 保存报告并清理**

在 `test-results/dashboard-share-permanent-link/README.md` 记录环境、场景结果、脱敏 URL、接口状态码、截图和 trace 路径。清理测试副本、临时画布和分享数据；不得记录完整 Token、sessionId 或密码。

---

## 执行顺序与停止条件

1. Task 1 必须先通过，建立不能回退的安全基线。
2. Task 2 只修改数据库形状和 Token，完成后立即运行模型与 Token 测试。
3. Task 3 只修改后端生命周期和管理端点；若分享查询、数据源过滤或跨账号隔离测试失败，停止继续，不进入前端修改。
4. Task 4 只精简前端管理 UI；若 Token 兑换、session 页面或 `shareMode` 类型检查失败，撤回本任务中超出管理 UI 的改动范围并定位原因。
5. Task 5 只在自动化回归全部通过后执行。

## 自审结果

- 计划以当前代码为基线，没有要求重新创建现有模型文件、分享页面、查询接口或权限链路。
- 每项删除都有明确文件、符号和保护测试。
- `share_view.py` 的数据查询和敏感字段过滤被明确列为保留区。
- `permission_cache.py` 不在本次修改范围，避免再次把普通缓存清理误判为撤权。
- 原有菜单守卫、页面高度、namespace 请求修复被纳入回归，但不重复实现。
- 链接和 session 的唯一键、Token 新签名和 API 新契约在模型、服务、前后端与测试中保持一致。
- 计划不包含 Git 提交操作。
