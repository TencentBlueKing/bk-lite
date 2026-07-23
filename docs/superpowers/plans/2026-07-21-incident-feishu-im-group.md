# Incident 飞书协作群 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Incident 协作区实现飞书一键建群、成员映射预检、只增不减的持续增员、状态管理、失败恢复和解绑，并在测试飞书租户完成完整流程验证。

**Architecture:** `system_mgmt` 增加通用 `im_group` Provider 能力和飞书实现，继续持有凭据、渠道访问和用户映射；`alerts` 持有 Incident 群绑定、成员快照、状态机和 Outbox，通过运行时门面调用飞书；Web 在现有协作页右侧栏增加独立群状态组件。建群、增员和摘要消息全部异步且幂等，`external_chat_id` 一经取得立即落库，持续同步只新增成员、不移除成员。

**Tech Stack:** Python 3.12、Django 4.2、Django REST Framework、Celery、pytest、requests、Next.js 16、React 19、TypeScript、Ant Design 5、react-intl、pnpm。

## Global Constraints

- 首期只实现飞书；不得加入企业微信伪实现、占位 Provider 或不可执行入口。
- 管理权限严格为 `request.user.username in incident.operator`；超级管理员也不能直接绕过，需先加入 Incident 负责人。
- 群成员为 `operator + collaborators` 去重集合；同一用户同时出现时角色取 `operator`。
- 成员同步只增不减；从 Incident 移除人员时不得调用飞书移除成员接口。
- 至少一名已映射负责人即可创建；未映射成员允许进入待处理状态。
- 一个 Incident 同时最多一个非 `unlinked` 绑定；更换渠道必须先解绑，解绑不删除外部群。
- `pending_create/creating` 阶段不允许取消或解绑；必须等待外部调用收敛。
- Incident 关闭时暂停自动增员，重新打开后仅在关闭前持续同步开启时自动对账；手工暂停不得被重开自动恢复。
- Incident 成员不得外键关联 `IMNotificationUserMapping`；只保存当次外部 ID 快照，并按用户名重新解析。
- 飞书成员标识固定使用所选渠道的 `external_receive_field`，只允许 `user_id` 或 `open_id`。
- 每次飞书建群/增员最多提交 50 个用户 ID；平台返回的无效 ID 必须落到具体成员。
- 新增/修改的后端代码覆盖率不低于 75%；禁止原生 SQL。
- 前端不得使用 `any`；新增文案全部进入 `react-intl`；颜色、间距、圆角使用 Ant Design 或项目 token。
- 不记录或返回飞书 app secret、tenant token、完整平台响应；日志只保留阶段、错误码、请求 ID 和人数。

---

## File Map

### System management

- Modify `server/apps/system_mgmt/providers/adapters/base.py`：定义通用 IM 群 Provider 操作合同。
- Modify `server/apps/system_mgmt/providers/adapters/feishu.py`：实现飞书建群、查群、增员和群消息。
- Modify `server/apps/system_mgmt/providers/manifests/feishu.py`：声明 `im_group` capability 和可覆盖 URL。
- Create `server/apps/system_mgmt/services/im_channel_access.py`：统一渠道 team 可见性规则。
- Create `server/apps/system_mgmt/services/im_group_service.py`：就绪渠道查询和 Provider 运行时门面。
- Modify `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`：复用公共渠道权限函数，消除两套规则。
- Create `server/apps/system_mgmt/tests/test_feishu_im_group_provider.py`：飞书 HTTP 合同和错误归一化测试。
- Create `server/apps/system_mgmt/tests/test_im_group_service.py`：渠道访问、就绪校验和运行时测试。

### Alerts backend

- Create `server/apps/alerts/models/incident_im.py`：群绑定和成员模型及状态枚举。
- Modify `server/apps/alerts/models/__init__.py`：导出新模型。
- Create `server/apps/alerts/migrations/0022_incident_im_group.py`：同时依赖两个现有 `0021` 叶子迁移并创建表。
- Create `server/apps/alerts/service/incident_im/errors.py`：稳定业务错误码和异常。
- Create `server/apps/alerts/service/incident_im/members.py`：成员去重、映射解析和只增不减对账。
- Create `server/apps/alerts/service/incident_im/groups.py`：创建、读取、设置、暂停、恢复、重试和解绑领域服务。
- Create `server/apps/alerts/service/incident_im/delivery.py`：Outbox 的建群、增员、摘要消息和失败收口。
- Create `server/apps/alerts/service/incident_im/reconcile.py`：人员变化、映射补齐和 Incident 状态联动。
- Create `server/apps/alerts/service/incident_im/__init__.py`：只导出稳定服务接口。
- Create `server/apps/alerts/serializers/incident_im.py`：请求和响应合同。
- Modify `server/apps/alerts/serializers/__init__.py`：导出新 serializer。
- Create `server/apps/alerts/views/incident_im.py`：嵌套 Incident IM 群 ViewSet。
- Modify `server/apps/alerts/views/__init__.py`、`server/apps/alerts/urls.py`：注册嵌套路由。
- Modify `server/apps/alerts/service/outbox.py`：分派 Incident IM 事件并在重试耗尽时收口。
- Modify `server/apps/alerts/tasks/tasks.py`、`server/apps/alerts/tasks/__init__.py`、`server/apps/alerts/config.py`：增加异步对账与周期扫描。
- Modify `server/apps/alerts/serializers/incident.py`：Incident 人员变化提交后触发对账。
- Modify `server/apps/alerts/service/incident_operator.py`：关闭/重开后触发群暂停/恢复。
- Create `server/apps/alerts/tests/test_incident_im_models.py`。
- Create `server/apps/alerts/tests/test_incident_im_members.py`。
- Create `server/apps/alerts/tests/test_incident_im_group_views.py`。
- Create `server/apps/alerts/tests/test_incident_im_delivery.py`。
- Create `server/apps/alerts/tests/test_incident_im_reconcile.py`。

### Web

- Modify `web/src/app/alarm/types/incidents.ts`：增加 IM 群 API 类型。
- Modify `web/src/app/alarm/api/incidents.ts`：增加群 API 方法并移除本次触及方法的 `any`。
- Create `web/src/app/alarm/(pages)/incidents/components/collaboration/imGroup/state.ts`：纯状态映射和轮询策略。
- Create `web/src/app/alarm/(pages)/incidents/components/collaboration/imGroup/useIncidentIMGroup.ts`：请求、轮询和独立 loading 状态。
- Create `web/src/app/alarm/(pages)/incidents/components/collaboration/imGroup/createModal.tsx`。
- Create `web/src/app/alarm/(pages)/incidents/components/collaboration/imGroup/memberDrawer.tsx`。
- Create `web/src/app/alarm/(pages)/incidents/components/collaboration/imGroup/confirmModals.tsx`。
- Create `web/src/app/alarm/(pages)/incidents/components/collaboration/imGroup/index.tsx`：紧凑状态卡及动作菜单。
- Modify `web/src/app/alarm/(pages)/incidents/components/collaboration/index.tsx`：挂载组件并联动人员变化。
- Modify `web/src/app/alarm/locales/zh.json`、`web/src/app/alarm/locales/en.json`：完整双语文案。
- Create `web/scripts/incident-im-group-ui-test.ts`、Modify `web/package.json`：纯状态与前端合同测试。

### Validation

- Create `docs/validation/incident-feishu-group-runbook.md`：测试租户准备、12 场景、证据和清理说明。
- Create `docs/reviews/incident-feishu-group-validation-2026-07-21.md`：真实验证结果记录。

---

### Task 1: 定义 IM 群 Provider 合同并实现飞书适配器

**Files:**
- Modify: `server/apps/system_mgmt/providers/adapters/base.py`
- Modify: `server/apps/system_mgmt/providers/adapters/feishu.py`
- Modify: `server/apps/system_mgmt/providers/manifests/feishu.py`
- Create: `server/apps/system_mgmt/tests/test_feishu_im_group_provider.py`

**Interfaces:**
- Consumes: `RuntimeApplicationService.execute(...)`、现有 `_fetch_tenant_access_token()` 和 `CapabilityExecutionResult`。
- Produces: `BaseIMGroupAdapter`；`FeishuIMGroupAdapter.create_group/get_group/add_members/send_group_message`；统一 payload 中的 `chat_id`、`invalid_member_ids`、`external_request_id`。

- [ ] **Step 1: 写 Provider 合同和飞书请求 RED 测试**

```python
from unittest import mock


def test_feishu_manifest_declares_im_group_capability():
    capability = PROVIDER_MANIFEST.get_capability("im_group")
    assert capability.adapter_key == "feishu.im_group"
    assert capability.adapter_path.endswith("FeishuIMGroupAdapter")


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.headers = {"X-Tt-Logid": "req-1"}

    def json(self):
        return self._payload


def test_create_group_sends_fixed_member_id_type_and_uuid():
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post",
        return_value=FakeResponse({"code": 0, "data": {"chat_id": "oc_1"}}),
    ) as post:
        result = FeishuIMGroupAdapter.create_group(
            config={"app_id": "app", "app_secret": "secret"},
            provider_key="feishu",
            capability_key="im_group",
            group_name="[INC-1] DB",
            owner_id="ou_owner",
            member_ids=["ou_owner", "ou_user"],
            member_id_type="open_id",
            idempotency_key="bklite-0123456789",
        )
    assert result.success is True
    assert result.payload["chat_id"] == "oc_1"
    request = post.call_args
    assert request.kwargs["params"] == {"user_id_type": "open_id"}
    assert request.kwargs["json"]["uuid"] == "bklite-0123456789"
    assert request.kwargs["json"]["set_bot_manager"] is True


def test_add_members_returns_invalid_ids_without_losing_successes():
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post",
        return_value=FakeResponse({"code": 0, "data": {"invalid_id_list": ["ou_bad"]}}),
    ):
        result = FeishuIMGroupAdapter.add_members(
            config={}, provider_key="feishu", capability_key="im_group",
            chat_id="oc_1", member_ids=["ou_ok", "ou_bad"], member_id_type="open_id",
        )
    assert result.success is True
    assert result.partial_success is True
    assert result.payload["invalid_member_ids"] == ["ou_bad"]
```

- [ ] **Step 2: 运行 RED 测试**

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/system_mgmt/tests/test_feishu_im_group_provider.py -q
```

Expected: FAIL，提示 `BaseIMGroupAdapter`、`FeishuIMGroupAdapter` 或 `im_group` capability 不存在。

- [ ] **Step 3: 添加通用合同和飞书实现**

在 `base.py` 增加完整基类：

```python
class BaseIMGroupAdapter(BaseCapabilityAdapter):
    capability_key = "im_group"

    @classmethod
    def create_group(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return CapabilityExecutionResult.not_implemented(capability_key, "create_group")

    @classmethod
    def get_group(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return CapabilityExecutionResult.not_implemented(capability_key, "get_group")

    @classmethod
    def add_members(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return CapabilityExecutionResult.not_implemented(capability_key, "add_members")

    @classmethod
    def send_group_message(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return CapabilityExecutionResult.not_implemented(capability_key, "send_group_message")
```

在飞书适配器中增加常量和 `FeishuIMGroupAdapter`。所有方法必须校验 `member_id_type in {"user_id", "open_id"}`、单批人数 `<= 50`，并通过已有 token helper 发请求：

```python
FEISHU_CREATE_CHAT_URL = "https://open.feishu.cn/open-apis/im/v1/chats"
FEISHU_CHAT_URL = "https://open.feishu.cn/open-apis/im/v1/chats/{chat_id}"
FEISHU_CHAT_MEMBERS_URL = "https://open.feishu.cn/open-apis/im/v1/chats/{chat_id}/members"


class FeishuIMGroupAdapter(BaseIMGroupAdapter):
    capability_key = "im_group"

    @classmethod
    def test_connection(cls, config, provider_key, capability_key, **kwargs):
        return _request_tenant_access_token(config, capability_key)

    @classmethod
    def create_group(cls, config, provider_key, capability_key, **kwargs):
        member_id_type = kwargs["member_id_type"]
        member_ids = list(dict.fromkeys(kwargs.get("member_ids") or []))
        validation_error = _validate_group_members(member_id_type, member_ids)
        if validation_error:
            return validation_error
        return _execute_feishu_group_request(
            config=config,
            method="post",
            url=_get_config_value(config, "im_group_create_chat_url", FEISHU_CREATE_CHAT_URL),
            params={"user_id_type": member_id_type},
            payload={
                "name": kwargs["group_name"],
                "owner_id": kwargs["owner_id"],
                "user_id_list": member_ids,
                "chat_mode": "group",
                "chat_type": "private",
                "set_bot_manager": True,
                "uuid": kwargs["idempotency_key"],
            },
            success_payload=lambda data, request_id: {
                "chat_id": str((data.get("data") or {}).get("chat_id") or ""),
                "external_request_id": request_id,
            },
        )
```

`get_group` 使用 GET chat URL；`add_members` 使用 POST members URL 和 `{"id_list": member_ids}`；`send_group_message` 复用消息 URL并固定 `receive_id_type=chat_id`。`_execute_feishu_group_request` 必须把 429/5xx/Timeout 归一为 `retryable=True`，401/403 为权限/鉴权终态错误，404 为 `provider.group_not_found`，并且日志不得包含 Authorization header。

在 manifest 增加 `im_group` capability，connection fields 为 `im_group_create_chat_url`、`im_group_chat_url`、`im_group_members_url`、`im_group_send_message_url`，默认值使用上述官方地址。

- [ ] **Step 4: 运行 GREEN 和 Provider 回归**

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/system_mgmt/tests/test_feishu_im_group_provider.py apps/system_mgmt/tests/test_provider_manifest.py apps/system_mgmt/tests/test_im_notification_manifest.py -q
```

Expected: PASS；新增测试覆盖成功、invalid ID、限流、权限不足、404、超时和敏感日志。

- [ ] **Step 5: 提交**

```bash
git add server/apps/system_mgmt/providers/adapters/base.py server/apps/system_mgmt/providers/adapters/feishu.py server/apps/system_mgmt/providers/manifests/feishu.py server/apps/system_mgmt/tests/test_feishu_im_group_provider.py
git commit -m "feat(system-mgmt): 增加飞书群协作能力"
```

### Task 2: 建立渠道访问与 IM 群运行时门面

**Files:**
- Create: `server/apps/system_mgmt/services/im_channel_access.py`
- Create: `server/apps/system_mgmt/services/im_group_service.py`
- Modify: `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`
- Create: `server/apps/system_mgmt/tests/test_im_group_service.py`
- Modify: `server/apps/system_mgmt/tests/test_im_notification_viewset.py`

**Interfaces:**
- Consumes: Task 1 的 `im_group` capability。
- Produces: `filter_accessible_im_channels(queryset, user)`、`can_access_im_channel(user, channel)`、`IMGroupRuntimeService.list_ready_channels(user)`、`require_ready_channel(user, channel_id)`、`execute(channel, operation, **kwargs)`。

- [ ] **Step 1: 写访问和就绪状态 RED 测试**

```python
@pytest.mark.django_db
def test_ready_channels_require_team_mapping_and_both_capabilities(user, channel):
    user.group_list = [{"id": channel.team[0]}]
    channel.integration_instance.capability_status = {
        "im_notification": "ready",
        "im_group": "ready",
    }
    channel.integration_instance.save(update_fields=["capability_status"])
    assert list(IMGroupRuntimeService.list_ready_channels(user)) == [channel]


@pytest.mark.django_db
def test_channel_with_mapping_ready_but_group_unverified_is_hidden(user, channel):
    channel.integration_instance.capability_status = {"im_notification": "ready"}
    channel.integration_instance.save(update_fields=["capability_status"])
    assert list(IMGroupRuntimeService.list_ready_channels(user)) == []
```

- [ ] **Step 2: 运行 RED 测试**

Run 与 Expected：

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/system_mgmt/tests/test_im_group_service.py -q
# Expected: FAIL，模块不存在。
```

- [ ] **Step 3: 实现公共访问函数和运行时服务**

```python
def get_user_group_ids(user) -> set[int] | None:
    if getattr(user, "is_superuser", False):
        return None
    return {int(item["id"]) for item in getattr(user, "group_list", []) if str(item.get("id", "")).isdigit()}


def can_access_im_channel(user, channel: IMNotificationChannel) -> bool:
    group_ids = get_user_group_ids(user)
    return group_ids is None or bool(group_ids.intersection({int(item) for item in channel.team or []}))
```

`IMGroupRuntimeService.require_ready_channel` 必须同时校验：渠道存在且启用、渠道 `status=ready`、Provider 为 `feishu`、集成实例启用且 `status=ready`、`im_notification=ready`、`im_group=ready`、用户有渠道 team 访问权。失败抛出带稳定 code 的 `IMGroupChannelError`，不返回模糊布尔值。

```python
class IMGroupRuntimeService:
    @staticmethod
    def execute(channel: IMNotificationChannel, operation: str, **kwargs) -> CapabilityExecutionResult:
        return RuntimeApplicationService().execute(
            provider_key=channel.integration_instance.provider_key,
            capability_key="im_group",
            operation=operation,
            config=channel.integration_instance.get_runtime_config(),
            channel=channel,
            **kwargs,
        )
```

修改 `IMNotificationChannelViewSet` 的团队过滤和单对象校验，调用公共函数，保持原 API 响应不变。

- [ ] **Step 4: 运行 GREEN 和渠道权限回归**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/system_mgmt/tests/test_im_group_service.py apps/system_mgmt/tests/test_im_notification_viewset.py -q
```

Expected: PASS，普通用户、无组织用户、跨组织用户、超级管理员及 capability 未就绪均有用例。

- [ ] **Step 5: 提交**

```bash
git add server/apps/system_mgmt/services/im_channel_access.py server/apps/system_mgmt/services/im_group_service.py server/apps/system_mgmt/viewset/im_notification_channel_viewset.py server/apps/system_mgmt/tests/test_im_group_service.py server/apps/system_mgmt/tests/test_im_notification_viewset.py
git commit -m "feat(system-mgmt): 提供群协作渠道运行时"
```

### Task 3: 创建 Incident 群绑定和成员模型

**Files:**
- Create: `server/apps/alerts/models/incident_im.py`
- Modify: `server/apps/alerts/models/__init__.py`
- Create: `server/apps/alerts/migrations/0022_incident_im_group.py`
- Create: `server/apps/alerts/tests/test_incident_im_models.py`

**Interfaces:**
- Consumes: `Incident`、`IMNotificationChannel`、`MaintainerInfo`、`TimeInfo`。
- Produces: `IncidentIMGroup`、`IncidentIMMember` 及嵌套 `Status/Stage/PauseReason/MappingStatus/SyncStatus/Role` 枚举。

- [ ] **Step 1: 写模型约束 RED 测试**

```python
import uuid


def make_group(incident, channel, status):
    return IncidentIMGroup.objects.create(
        incident=incident,
        channel=channel,
        provider_key="feishu",
        channel_name_snapshot=channel.name,
        member_id_type="open_id",
        group_name=f"[INC-{incident.id}] test-{uuid.uuid4().hex[:8]}",
        status=status,
        idempotency_key=f"bklite-{uuid.uuid4().hex}",
    )


@pytest.mark.django_db
def test_incident_has_only_one_non_unlinked_im_group(incident, channel):
    make_group(incident, channel, status=IncidentIMGroup.Status.ACTIVE)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_group(incident, channel, status=IncidentIMGroup.Status.PENDING_CREATE)


@pytest.mark.django_db
def test_unlinked_history_allows_new_binding(incident, channel):
    make_group(incident, channel, status=IncidentIMGroup.Status.UNLINKED)
    current = make_group(incident, channel, status=IncidentIMGroup.Status.PENDING_CREATE)
    assert current.status == IncidentIMGroup.Status.PENDING_CREATE


@pytest.mark.django_db
def test_member_identity_is_snapshot_not_mapping_foreign_key(group):
    field_names = {field.name for field in IncidentIMMember._meta.fields}
    assert "mapping" not in field_names
    assert {"username", "external_id", "external_id_type"} <= field_names
```

- [ ] **Step 2: 运行 RED**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_incident_im_models.py -q
# Expected: FAIL，模型不存在。
```

- [ ] **Step 3: 实现模型**

`IncidentIMGroup` 继承 `MaintainerInfo, TimeInfo`，字段使用规格中的名称。核心状态必须精确定义：

```python
class IncidentIMGroup(MaintainerInfo, TimeInfo):
    class Status(models.TextChoices):
        PENDING_CREATE = "pending_create", "待创建"
        CREATING = "creating", "创建中"
        ACTIVE = "active", "正常"
        ACTIVE_PARTIAL = "active_partial", "部分成功"
        PAUSED = "paused", "已暂停"
        DEGRADED = "degraded", "配置异常"
        CREATE_FAILED = "create_failed", "创建失败"
        UNLINKED = "unlinked", "已解绑"

    class Stage(models.TextChoices):
        QUEUED = "queued", "已提交"
        CREATING_CHAT = "creating_chat", "创建群"
        ADDING_MEMBERS = "adding_members", "邀请成员"
        SENDING_SUMMARY = "sending_summary", "发送摘要"
        COMPLETED = "completed", "已完成"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey("alerts.Incident", on_delete=models.CASCADE, related_name="im_groups")
    channel = models.ForeignKey("system_mgmt.IMNotificationChannel", null=True, blank=True, on_delete=models.SET_NULL, related_name="incident_im_groups")
    provider_key = models.CharField(max_length=32, default="feishu")
    channel_name_snapshot = models.CharField(max_length=100)
    member_id_type = models.CharField(max_length=32)
    group_name = models.CharField(max_length=255)
    external_chat_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    external_owner_id = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING_CREATE, db_index=True)
    current_stage = models.CharField(max_length=32, choices=Stage.choices, default=Stage.QUEUED)
    continuous_sync_enabled = models.BooleanField(default=True)
    resume_after_reopen = models.BooleanField(default=False)
    pause_reason = models.CharField(max_length=32, blank=True, default="")
    idempotency_key = models.CharField(max_length=50, unique=True)
    last_error_code = models.CharField(max_length=128, blank=True, default="")
    last_error_message = models.CharField(max_length=500, blank=True, default="")
    last_sync_at = models.DateTimeField(null=True, blank=True)
    unlinked_at = models.DateTimeField(null=True, blank=True)
    unlinked_by = models.CharField(max_length=32, blank=True, default="")
```

`IncidentIMMember` 定义角色、映射和同步枚举，唯一约束 `(group, username)`；为 `(group, sync_status)` 和 `(group, mapping_status)` 建索引。群模型增加条件唯一约束：`fields=["incident"]`、`condition=~Q(status="unlinked")`。文件显式导入 `uuid`，保证后续 `group.id.hex` 可用于飞书幂等键。

- [ ] **Step 4: 生成并检查迁移**

```bash
cd server && INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run python manage.py makemigrations alerts --name incident_im_group
```

Expected: 生成 `0022_incident_im_group.py`，dependencies 同时包含：

```python
dependencies = [
    ("alerts", "0021_activealertfingerprint"),
    ("alerts", "0021_notifyresult_failure_reason"),
    ("system_mgmt", "0038_imnotificationchannel_imnotificationusermapping"),
]
```

不得生成数据迁移或 raw SQL。

- [ ] **Step 5: 运行 GREEN、迁移检查和提交**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_incident_im_models.py -q
cd server && INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run python manage.py makemigrations --check --dry-run
git add server/apps/alerts/models/incident_im.py server/apps/alerts/models/__init__.py server/apps/alerts/migrations/0022_incident_im_group.py server/apps/alerts/tests/test_incident_im_models.py
git commit -m "feat(alerts): 增加 Incident 群绑定模型"
```

Expected: 测试 PASS，`makemigrations --check` 输出 `No changes detected`。

### Task 4: 实现成员映射解析与只增不减对账

**Files:**
- Create: `server/apps/alerts/service/incident_im/__init__.py`
- Create: `server/apps/alerts/service/incident_im/errors.py`
- Create: `server/apps/alerts/service/incident_im/members.py`
- Create: `server/apps/alerts/tests/test_incident_im_members.py`

**Interfaces:**
- Consumes: Task 3 模型、`IMNotificationUserMapping`、最近一次 `IMNotificationSyncRun.payload.conflict_issues`。
- Produces: `ResolvedIncidentMember`、`resolve_incident_members(incident, channel)`、`reconcile_member_snapshots(group, incident)`、`get_pending_members(group)`。

- [ ] **Step 1: 写映射与只增不减 RED 测试**

```python
@pytest.mark.django_db
def test_resolver_deduplicates_operator_and_collaborator_and_prefers_operator(incident, channel, mapping):
    incident.operator = ["alice"]
    incident.collaborators = ["alice", "bob"]
    members = resolve_incident_members(incident, channel)
    assert [(item.username, item.role) for item in members] == [
        ("alice", "operator"),
        ("bob", "collaborator"),
    ]


@pytest.mark.django_db
def test_mapping_uses_mapping_receive_key_snapshot(incident, channel, mapping):
    mapping.external_receive_key = "open_id"
    mapping.external_snapshot = {"open_id": "ou_alice", "user_id": "u_alice"}
    mapping.save()
    member = resolve_incident_members(incident, channel)[0]
    assert member.external_id_type == "open_id"
    assert member.external_id == "ou_alice"


@pytest.mark.django_db
def test_reconcile_never_deletes_member_removed_from_incident(group, joined_member):
    group.incident.operator = []
    group.incident.collaborators = []
    group.incident.save(update_fields=["operator", "collaborators"])
    reconcile_member_snapshots(group, group.incident)
    assert group.members.get(username=joined_member.username).sync_status == "joined"
```

- [ ] **Step 2: 运行 RED**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_incident_im_members.py -q
# Expected: FAIL，resolver 不存在。
```

- [ ] **Step 3: 实现解析数据结构和错误类型**

```python
@dataclass(frozen=True)
class ResolvedIncidentMember:
    username: str
    role: str
    display_name: str
    mapping_status: str
    external_id: str
    external_id_type: str
    error_code: str
    error_message: str


class IncidentIMError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
```

解析时一次查询所有 BK-Lite User 和渠道 mappings；没有 mapping 但最近同步冲突项的 `platform_user_ids` 包含该用户 ID 时标为 `conflict`，否则为 `unmapped`。映射存在但快照中缺少配置的 receive key 时标为 `unmapped/IM_USER_RECEIVE_ID_MISSING`。结果按 operator 优先、username 排序。

`reconcile_member_snapshots` 只 `bulk_create` 新用户名并更新既有角色/映射快照；不得删除或把已 `joined` 成员改回 waiting。只有非 joined 成员在映射补齐时从 waiting 转 pending。

- [ ] **Step 4: 运行 GREEN 和覆盖率**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_incident_im_members.py --cov=apps.alerts.service.incident_im.members --cov-report=term-missing --cov-fail-under=75 -q
```

Expected: PASS，目标模块覆盖率 ≥75%。

- [ ] **Step 5: 提交**

```bash
git add server/apps/alerts/service/incident_im server/apps/alerts/tests/test_incident_im_members.py
git commit -m "feat(alerts): 解析 Incident 飞书成员映射"
```

### Task 5: 实现创建、查询和成员预览 API

**Files:**
- Create: `server/apps/alerts/service/incident_im/groups.py`
- Create: `server/apps/alerts/serializers/incident_im.py`
- Modify: `server/apps/alerts/serializers/__init__.py`
- Create: `server/apps/alerts/views/incident_im.py`
- Modify: `server/apps/alerts/views/__init__.py`
- Modify: `server/apps/alerts/urls.py`
- Create: `server/apps/alerts/tests/test_incident_im_group_views.py`

**Interfaces:**
- Consumes: Task 2 的渠道门面、Task 3 模型、Task 4 resolver、`enqueue_outbox`。
- Produces: 嵌套路由 `/alerts/api/incident/{incident_pk}/im-group/` 及 `options/members/retry/pause/resume` actions；`IncidentIMGroupService.create`。

- [ ] **Step 1: 写权限、预览、创建和并发 RED 测试**

```python
@pytest.mark.django_db
def test_collaborator_can_read_group_but_cannot_load_options_or_create(api_client, collaborator, incident):
    api_client.force_authenticate(collaborator)
    group_url = f"/api/v1/alerts/api/incident/{incident.id}/im-group/"
    options_url = f"{group_url}options/"
    payload = {"channel_id": 1, "group_name": "[INC-1] DB", "owner_username": "owner", "continuous_sync_enabled": True}
    assert api_client.get(group_url).status_code == 200
    assert api_client.get(options_url).status_code == 403
    assert api_client.post(group_url, payload, format="json").status_code == 403


@pytest.mark.django_db
def test_superuser_not_in_operator_cannot_create_group(api_client, superuser, incident, channel):
    api_client.force_authenticate(superuser)
    url = f"/api/v1/alerts/api/incident/{incident.id}/im-group/"
    payload = {"channel_id": channel.id, "group_name": "[INC-1] DB", "owner_username": "owner", "continuous_sync_enabled": True}
    response = api_client.post(url, payload, format="json")
    assert response.status_code == 403
    assert response.json()["code"] == "IM_OPERATOR_REQUIRED"


@pytest.mark.django_db(transaction=True)
def test_duplicate_create_returns_conflict_and_one_binding(api_client, operator, incident, channel):
    api_client.force_authenticate(operator)
    url = f"/api/v1/alerts/api/incident/{incident.id}/im-group/"
    payload = {"channel_id": channel.id, "group_name": "[INC-1] DB", "owner_username": operator.username, "continuous_sync_enabled": True}
    first = api_client.post(url, payload, format="json")
    second = api_client.post(url, payload, format="json")
    assert first.status_code == 202
    assert second.status_code == 409
    assert IncidentIMGroup.objects.filter(incident=incident).count() == 1
```

- [ ] **Step 2: 运行 RED**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_incident_im_group_views.py -q
# Expected: FAIL，路由 404。
```

- [ ] **Step 3: 实现 serializer 和领域创建**

请求 serializer：

```python
class IncidentIMGroupCreateSerializer(serializers.Serializer):
    channel_id = serializers.IntegerField(min_value=1)
    group_name = serializers.CharField(min_length=1, max_length=255, trim_whitespace=True)
    owner_username = serializers.CharField(max_length=32)
    continuous_sync_enabled = serializers.BooleanField(default=True)


class IncidentIMGroupSettingsSerializer(serializers.Serializer):
    continuous_sync_enabled = serializers.BooleanField()


class IncidentIMGroupUnlinkSerializer(serializers.Serializer):
    group_name = serializers.CharField(max_length=255)
```

`IncidentIMGroupService.create` 必须在一个 `transaction.atomic()` 内：锁定 Incident、再次检查 actor 为当前 operator、验证 Incident 在 `ACTIVATE_STATUS`、取得就绪渠道、解析成员、验证 owner 是 mapped operator、创建 group/member 快照、创建 Outbox。幂等键固定为 `bklite-{group.id.hex}`；Outbox key 为 `incident-im-group:{group.id}:create`。

- [ ] **Step 4: 实现嵌套 ViewSet 和响应合同**

注册：

```python
router.register(
    r"api/incident/(?P<incident_pk>\d+)/im-group",
    IncidentIMGroupViewSet,
    basename="incident-im-group",
)
```

ViewSet 的 `list` 返回当前群对象或 `null`，`create` 返回 202，`partial_update` 修改持续同步，`destroy` 校验群名后解绑。`options` 无 `channel_id` 时返回可用渠道和默认群名；带 `channel_id` 时额外返回 owner candidates 和成员预览。`members` 使用 `CustomPageNumberPagination`。

所有写方法同时使用 `@HasPermission("Incidents-Edit")` 和 service operator 校验；读方法使用 `Incidents-View` 和 Incident 数据范围过滤。异常统一返回：

```json
{"code": "IM_NO_MAPPED_OPERATOR", "message": "至少需要一名已映射的负责人", "details": {}}
```

- [ ] **Step 5: 运行 GREEN 和 API 回归**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_incident_im_group_views.py apps/alerts/tests/test_incident_update_views.py apps/alerts/tests/test_incident_serializer_methods.py -q
```

Expected: PASS；覆盖 owner、collaborator、无关用户、超级管理员、跨组织渠道、无映射、部分映射、重复创建和已关闭 Incident。

- [ ] **Step 6: 提交**

```bash
git add server/apps/alerts/service/incident_im/groups.py server/apps/alerts/serializers/incident_im.py server/apps/alerts/serializers/__init__.py server/apps/alerts/views/incident_im.py server/apps/alerts/views/__init__.py server/apps/alerts/urls.py server/apps/alerts/tests/test_incident_im_group_views.py
git commit -m "feat(alerts): 提供 Incident 飞书群 API"
```

### Task 6: 实现 Outbox 建群、增员和摘要消息

**Files:**
- Create: `server/apps/alerts/service/incident_im/delivery.py`
- Modify: `server/apps/alerts/service/outbox.py`
- Create: `server/apps/alerts/tests/test_incident_im_delivery.py`
- Modify: `server/apps/alerts/tests/test_outbox.py`

**Interfaces:**
- Consumes: Task 1 Provider、Task 2 runtime、Task 3 状态、Task 4 pending members。
- Produces: `deliver_create_group(group_id)`、`deliver_add_members(group_id)`、`deliver_summary(group_id)`、`handle_delivery_exhausted(kind, payload, error)`。

- [ ] **Step 1: 写崩溃边界、幂等和部分失败 RED 测试**

```python
from unittest import mock

from apps.system_mgmt.providers.runtime import CapabilityExecutionResult


@pytest.mark.django_db
def test_chat_id_is_saved_before_followup_events(group):
    result = CapabilityExecutionResult.success_result("created", payload={"chat_id": "oc_1", "invalid_member_ids": []})
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=result), mock.patch(
        "apps.alerts.service.incident_im.delivery.enqueue_outbox"
    ) as enqueue:
        deliver_create_group(group.id)
    group.refresh_from_db()
    assert group.external_chat_id == "oc_1"
    assert enqueue.call_args.args[0] == "incident_im_group.add_members"


@pytest.mark.django_db
def test_create_retry_with_existing_chat_id_never_calls_create(group):
    group.external_chat_id = "oc_existing"
    group.save(update_fields=["external_chat_id"])
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute") as execute:
        deliver_create_group(group.id)
    execute.assert_not_called()


@pytest.mark.django_db
def test_add_members_marks_only_invalid_ids_failed(group, pending_members):
    result = CapabilityExecutionResult(
        success=True, partial_success=True, summary="partial",
        payload={"invalid_member_ids": [pending_members[1].external_id]},
    )
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=result):
        deliver_add_members(group.id)
    states = dict(group.members.values_list("username", "sync_status"))
    assert states == {pending_members[0].username: "joined", pending_members[1].username: "failed"}
```

- [ ] **Step 2: 运行 RED**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_incident_im_delivery.py -q
# Expected: FAIL，delivery 不存在。
```

- [ ] **Step 3: 实现串行事件链**

建群 handler 的顺序固定为：锁定并把状态改为 creating/current_stage=creating_chat；调用飞书；立即保存 `external_chat_id`；标记首批有效成员 joined；入队 add_members。初始成员按 owner 优先去重后取前 50 人。

增员 handler 每次只读取 `pending/failed` 且已 mapped 的成员，以 50 人切批。每批成功后立即提交成员状态；网络异常重投时只会再次处理未 joined 成员。处理完入队 send_summary。摘要 handler 成功后设置 stage completed，并根据是否仍有 waiting/failed 决定 active 或 active_partial。

```python
OUTBOX_CREATE = "incident_im_group.create"
OUTBOX_ADD_MEMBERS = "incident_im_group.add_members"
OUTBOX_SEND_SUMMARY = "incident_im_group.send_summary"
OUTBOX_RECONCILE = "incident_im_group.reconcile"


def _deliver_payload(kind: str, payload: dict) -> None:
    if kind == OUTBOX_CREATE:
        deliver_create_group(int(payload["group_id"]))
        return
    if kind == OUTBOX_ADD_MEMBERS:
        deliver_add_members(int(payload["group_id"]))
        return
    if kind == OUTBOX_SEND_SUMMARY:
        deliver_summary(int(payload["group_id"]))
        return
```

Provider `retryable=True` 时抛出 `IncidentIMRetryableError` 让 Outbox 重试；终态错误更新成员/群状态后正常返回，使 Outbox delivered。外部群 404 必须置 degraded，不得调用 create_group。

- [ ] **Step 4: 增加重试耗尽收口**

修改 `deliver_outbox_record`：当 attempts 达到 max 且异常将导致 FAILED 时，事务提交后调用 `handle_delivery_exhausted`。无 chat ID 时置 `create_failed`；有 chat ID 时置 `active_partial` 或 `degraded`。收口自身失败只记异常日志，不能把 Outbox 从 FAILED 改回 pending。

- [ ] **Step 5: 运行 GREEN、Outbox 回归和覆盖率**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_incident_im_delivery.py apps/alerts/tests/test_outbox.py --cov=apps.alerts.service.incident_im.delivery --cov=apps.alerts.service.outbox --cov-report=term-missing --cov-fail-under=75 -q
```

Expected: PASS；覆盖创建 ACK 丢失、部分成员失败、摘要失败、限流重试、重试耗尽和外部群不存在。

- [ ] **Step 6: 提交**

```bash
git add server/apps/alerts/service/incident_im/delivery.py server/apps/alerts/service/outbox.py server/apps/alerts/tests/test_incident_im_delivery.py server/apps/alerts/tests/test_outbox.py
git commit -m "feat(alerts): 异步投递 Incident 飞书群"
```

### Task 7: 实现持续同步和 Incident 生命周期联动

**Files:**
- Create: `server/apps/alerts/service/incident_im/reconcile.py`
- Modify: `server/apps/alerts/serializers/incident.py`
- Modify: `server/apps/alerts/service/incident_operator.py`
- Modify: `server/apps/alerts/tasks/tasks.py`
- Modify: `server/apps/alerts/tasks/__init__.py`
- Modify: `server/apps/alerts/config.py`
- Create: `server/apps/alerts/tests/test_incident_im_reconcile.py`
- Modify: `server/apps/alerts/tests/test_incident_operator.py`

**Interfaces:**
- Consumes: Task 4 snapshot reconcile、Task 6 Outbox events。
- Produces: `reconcile_incident_im_group(incident_id, force_delivery=False)`、`pause_group_for_closed_incident(incident_id)`、`resume_group_for_reopened_incident(incident_id)`、Celery tasks。

- [ ] **Step 1: 写新增、删除、映射补齐和关闭/重开 RED 测试**

```python
@pytest.mark.django_db
def test_new_collaborator_enqueues_add_when_continuous_sync_enabled(group, incident, mapping):
    incident.collaborators = ["new-user"]
    incident.save(update_fields=["collaborators"])
    reconcile_incident_im_group(incident.id)
    assert group.members.get(username="new-user").sync_status == "pending"
    assert AlertOutbox.objects.filter(kind="incident_im_group.add_members").exists()


@pytest.mark.django_db
def test_removed_collaborator_is_not_deleted_or_enqueued_for_removal(group, joined_member):
    group.incident.collaborators = []
    group.incident.save(update_fields=["collaborators"])
    reconcile_incident_im_group(group.incident_id)
    assert group.members.filter(pk=joined_member.pk, sync_status="joined").exists()
    assert not AlertOutbox.objects.filter(kind__contains="remove").exists()


@pytest.mark.django_db
def test_reopen_preserves_manual_pause_but_resumes_closed_pause(manual_paused_group, closed_paused_group):
    resume_group_for_reopened_incident(manual_paused_group.incident_id)
    resume_group_for_reopened_incident(closed_paused_group.incident_id)
    manual_paused_group.refresh_from_db()
    closed_paused_group.refresh_from_db()
    assert manual_paused_group.pause_reason == "manual"
    assert closed_paused_group.pause_reason == ""
```

- [ ] **Step 2: 运行 RED**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_incident_im_reconcile.py -q
# Expected: FAIL，reconcile 不存在。
```

- [ ] **Step 3: 实现对账和周期扫描**

`reconcile_incident_im_group` 锁定当前绑定，调用 `reconcile_member_snapshots`。持续同步开启、非暂停且 Incident 活跃时入队 add_members；关闭或暂停时只保留 waiting/pending 状态。`force_delivery=True` 用于手工重试，允许持续同步关闭，但仍禁止 Incident closed 或 manual paused 状态下投递。

增加 Celery task：

```python
@shared_task
def reconcile_waiting_incident_im_groups():
    group_ids = list(
        IncidentIMGroup.objects.filter(
            continuous_sync_enabled=True,
            status__in=[IncidentIMGroup.Status.ACTIVE, IncidentIMGroup.Status.ACTIVE_PARTIAL],
        ).order_by("last_sync_at", "pk").values_list("pk", flat=True)[:200]
    )
    for group_id in group_ids:
        reconcile_incident_im_group_by_group_id(group_id)
    return {"scheduled": len(group_ids)}
```

在 `alerts/config.py` 每分钟执行一次。任务必须逐群隔离异常，不得因为一个坏渠道停止剩余群。

- [ ] **Step 4: 接入 Incident 人员更新与生命周期**

`IncidentModelSerializer.update` 在确认 `operator` 或 `collaborators` 出现在 `validated_data` 时，在同一事务中创建 `incident_im_group.reconcile` Outbox；dedupe key 使用本次 Incident `updated_at` 微秒值，保证 broker 故障后仍能由周期 dispatcher 恢复。`IncidentOperator._close_incident` 在同一数据库事务中调用 close hook；`_reopen_incident` 同步清理 pause 并创建 reconcile Outbox。不要仅依赖 `transaction.on_commit(...delay)`，因为持续同步关闭时 broker 丢失将没有周期扫描补偿。

关闭逻辑：非 manual pause 的有效群一律置 `paused/incident_closed`，`resume_after_reopen=continuous_sync_enabled`。重开逻辑：manual pause 不变；incident_closed 清空 pause，按成员结果恢复 active/active_partial，仅 `resume_after_reopen=True` 时自动入队对账。

- [ ] **Step 5: 运行 GREEN 和 Incident 回归**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_incident_im_reconcile.py apps/alerts/tests/test_incident_operator.py apps/alerts/tests/test_incident_update_views.py -q
```

Expected: PASS；显式证明新增自动拉、关闭同步只等待、删除不踢、映射补齐自动拉、关闭暂停、重开恢复和手工暂停保持。

- [ ] **Step 6: 提交**

```bash
git add server/apps/alerts/service/incident_im/reconcile.py server/apps/alerts/serializers/incident.py server/apps/alerts/service/incident_operator.py server/apps/alerts/tasks/tasks.py server/apps/alerts/tasks/__init__.py server/apps/alerts/config.py server/apps/alerts/tests/test_incident_im_reconcile.py server/apps/alerts/tests/test_incident_operator.py
git commit -m "feat(alerts): 持续同步 Incident 飞书成员"
```

### Task 8: 完成管理操作、审计和外部漂移恢复

**Files:**
- Modify: `server/apps/alerts/service/incident_im/groups.py`
- Modify: `server/apps/alerts/views/incident_im.py`
- Modify: `server/apps/alerts/serializers/incident_im.py`
- Modify: `server/apps/alerts/tests/test_incident_im_group_views.py`
- Modify: `server/apps/alerts/tests/test_incident_im_delivery.py`

**Interfaces:**
- Consumes: 前述完整状态机。
- Produces: 持续同步 PATCH、retry/pause/resume actions、DELETE unlink、统一操作日志和 degraded recheck。

- [ ] **Step 1: 写状态转换和审计 RED 测试**

```python
from unittest import mock

from apps.system_mgmt.providers.runtime import CapabilityExecutionResult


@pytest.mark.django_db
def test_pause_and_resume_are_operator_only_and_audited(api_client, operator, active_group):
    api_client.force_authenticate(operator)
    assert api_client.post(pause_url(active_group.incident)).status_code == 200
    active_group.refresh_from_db()
    assert active_group.status == "paused"
    assert active_group.pause_reason == "manual"
    assert OperatorLog.objects.filter(target_id=active_group.incident.incident_id, overview__contains="暂停飞书群同步").exists()


@pytest.mark.django_db
def test_unlink_rejects_creating_and_requires_exact_group_name(api_client, operator, group):
    api_client.force_authenticate(operator)
    url = f"/api/v1/alerts/api/incident/{group.incident_id}/im-group/"
    group.status = "creating"
    group.save(update_fields=["status"])
    assert api_client.delete(url, data={"group_name": group.group_name}, format="json").status_code == 409
    group.status = "active"
    group.save(update_fields=["status"])
    assert api_client.delete(url, data={"group_name": "wrong"}, format="json").status_code == 400


@pytest.mark.django_db
def test_group_not_found_marks_degraded_without_recreating(group):
    result = CapabilityExecutionResult.failed_result("not found", code="provider.group_not_found")
    with mock.patch("apps.alerts.service.incident_im.groups.IMGroupRuntimeService.execute", return_value=result) as execute:
        retry_group(group, actor_username=group.incident.operator[0])
    group.refresh_from_db()
    assert group.status == "degraded"
    assert [call.kwargs["operation"] for call in execute.call_args_list] == ["get_group"]
```

- [ ] **Step 2: 运行 RED**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_incident_im_group_views.py apps/alerts/tests/test_incident_im_delivery.py -q
# Expected: 新管理行为 FAIL。
```

- [ ] **Step 3: 实现操作和审计**

`set_continuous_sync` 开启后立即对账，关闭只改变配置；`pause` 仅允许 active/active_partial；`resume` 仅允许 manual pause，并立即对账；`retry` 对 degraded 先调用 get_group，对正常/部分成功重新解析待处理成员；`unlink` 拒绝 pending/creating、非 completed stage 或存在 adding 成员，返回 `IM_GROUP_BUSY`，严格比对群名后置 unlinked。Outbox handler 遇到 unlinked 必须无外部调用直接成功，因此不删除、不伪造已投递状态，也不调用任何飞书删除 API。

每个动作调用 `record_operator_log`，`target_type=LogTargetType.INCIDENT`，overview 分别为创建、创建结果、持续同步设置、暂停、恢复、重试、补拉结果、解绑。成员结果审计只写成功/失败数量，不写外部 ID 列表。

- [ ] **Step 4: 运行 GREEN 和后端功能组合**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_incident_im_models.py apps/alerts/tests/test_incident_im_members.py apps/alerts/tests/test_incident_im_group_views.py apps/alerts/tests/test_incident_im_delivery.py apps/alerts/tests/test_incident_im_reconcile.py apps/alerts/tests/test_outbox.py -q
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add server/apps/alerts/service/incident_im/groups.py server/apps/alerts/views/incident_im.py server/apps/alerts/serializers/incident_im.py server/apps/alerts/tests/test_incident_im_group_views.py server/apps/alerts/tests/test_incident_im_delivery.py
git commit -m "feat(alerts): 管理 Incident 飞书群状态"
```

### Task 9: 定义 Web API 类型、状态映射与轮询策略

**Files:**
- Modify: `web/src/app/alarm/types/incidents.ts`
- Modify: `web/src/app/alarm/api/incidents.ts`
- Create: `web/src/app/alarm/(pages)/incidents/components/collaboration/imGroup/state.ts`
- Create: `web/scripts/incident-im-group-ui-test.ts`
- Modify: `web/package.json`

**Interfaces:**
- Consumes: Task 5/8 API。
- Produces: `IncidentIMGroup`、`IncidentIMMember`、`IncidentIMGroupOptions`、`deriveIMGroupView()`、`getIMGroupPollDelay()` 以及 API methods。

- [ ] **Step 1: 写纯状态 RED 测试**

```typescript
import assert from 'node:assert/strict';
import { deriveIMGroupView, getIMGroupPollDelay } from '../src/app/alarm/(pages)/incidents/components/collaboration/imGroup/state';

assert.deepEqual(
  deriveIMGroupView({ status: 'active_partial', pause_reason: null, member_summary: { total: 7, joined: 4, waiting: 2, failed: 1 } }),
  { label: 'partial', primaryAction: 'retry', canPollFast: false },
);
assert.equal(getIMGroupPollDelay('creating', 10_000, true), 2_000);
assert.equal(getIMGroupPollDelay('creating', 40_000, true), 5_000);
assert.equal(getIMGroupPollDelay('active', 40_000, true), null);
assert.equal(getIMGroupPollDelay('creating', 10_000, false), null);
```

- [ ] **Step 2: 运行 RED**

```bash
cd web && pnpm exec tsx scripts/incident-im-group-ui-test.ts
# Expected: FAIL，state 模块不存在。
```

- [ ] **Step 3: 添加严格类型和 API 方法**

类型必须包含：

```typescript
export type IncidentIMGroupStatus = 'pending_create' | 'creating' | 'active' | 'active_partial' | 'paused' | 'degraded' | 'create_failed';
export type IncidentIMMappingStatus = 'mapped' | 'unmapped' | 'conflict';
export type IncidentIMSyncStatus = 'waiting' | 'pending' | 'adding' | 'joined' | 'failed';

export interface IncidentIMPermissions {
  can_manage: boolean;
  can_retry: boolean;
  can_pause: boolean;
  can_resume: boolean;
  can_unlink: boolean;
}

export interface IncidentIMGroup {
  id: string;
  provider: 'feishu';
  group_name: string;
  external_chat_id: string;
  status: IncidentIMGroupStatus;
  current_stage: 'queued' | 'creating_chat' | 'adding_members' | 'sending_summary' | 'completed';
  pause_reason: 'manual' | 'incident_closed' | null;
  continuous_sync_enabled: boolean;
  member_summary: { total: number; joined: number; waiting: number; failed: number };
  permissions: IncidentIMPermissions;
  last_sync_at: string | null;
  open_chat_url: string | null;
}
```

在 `useIncidentsApi` 增加严格参数的 `getIncidentIMGroup/getIncidentIMGroupOptions/createIncidentIMGroup/updateIncidentIMGroup/getIncidentIMMembers/retryIncidentIMGroup/pauseIncidentIMGroup/resumeIncidentIMGroup/unlinkIncidentIMGroup`。DELETE 使用 `{ data: { group_name: groupName } }`。

- [ ] **Step 4: 实现纯状态函数**

`deriveIMGroupView` 只做后端状态到 UI label/primaryAction 映射；`pending/adding` 成员存在时增加 syncing 提示但不制造新后端状态。`getIMGroupPollDelay` 按已确认的 2s/5s/隐藏停止规则返回 number 或 null。

- [ ] **Step 5: 运行 GREEN、type-check 和提交**

```bash
cd web && pnpm exec tsx scripts/incident-im-group-ui-test.ts
cd web && pnpm type-check
git add web/src/app/alarm/types/incidents.ts web/src/app/alarm/api/incidents.ts web/src/app/alarm/'(pages)'/incidents/components/collaboration/imGroup/state.ts web/scripts/incident-im-group-ui-test.ts web/package.json
git commit -m "feat(web): 定义 Incident 飞书群前端合同"
```

Expected: 纯状态测试和 type-check PASS。

### Task 10: 实现协作页群状态卡、Modal 和 Drawer

**Files:**
- Create: `web/src/app/alarm/(pages)/incidents/components/collaboration/imGroup/useIncidentIMGroup.ts`
- Create: `web/src/app/alarm/(pages)/incidents/components/collaboration/imGroup/createModal.tsx`
- Create: `web/src/app/alarm/(pages)/incidents/components/collaboration/imGroup/memberDrawer.tsx`
- Create: `web/src/app/alarm/(pages)/incidents/components/collaboration/imGroup/confirmModals.tsx`
- Create: `web/src/app/alarm/(pages)/incidents/components/collaboration/imGroup/index.tsx`
- Modify: `web/src/app/alarm/(pages)/incidents/components/collaboration/index.tsx`
- Modify: `web/src/app/alarm/locales/zh.json`
- Modify: `web/src/app/alarm/locales/en.json`
- Modify: `web/scripts/incident-im-group-ui-test.ts`

**Interfaces:**
- Consumes: Task 9 类型/API/状态函数、现有 `incidentPk`、`incidentDetail`、`onRefresh`。
- Produces: `<IncidentIMGroupPanel incidentPk incidentDetail refreshVersion />`；父组件通过递增 `refreshVersion` 通知群卡片重新拉取。

- [ ] **Step 1: 扩充前端合同 RED 测试**

测试脚本读取组件和 locale，明确验证：状态卡挂载在协作者标题之前；Modal 使用 channel/group_name/owner/continuous fields；Drawer 使用分页成员 API；创建中 hook 清理 timer/AbortController；中英文拥有相同 key；移除确认含“不自动从飞书群移除”的 key。

```typescript
const getNested = (root: unknown, path: string): unknown =>
  path.split('.').reduce<unknown>((value, key) => {
    if (typeof value !== 'object' || value === null || !(key in value)) return undefined;
    return (value as Record<string, unknown>)[key];
  }, root);

for (const locale of [zh, en]) {
  for (const key of [
    'imGroup.title', 'imGroup.create', 'imGroup.creating', 'imGroup.active',
    'imGroup.partial', 'imGroup.paused', 'imGroup.incidentClosed',
    'imGroup.degraded', 'imGroup.viewDetails', 'imGroup.retry',
    'imGroup.unlinkConfirm', 'imGroup.removeCollaboratorWarning',
  ]) assert.equal(typeof getNested(locale.incidents, key), 'string', `missing incidents.${key}`);
}
```

- [ ] **Step 2: 运行 RED**

```bash
cd web && pnpm exec tsx scripts/incident-im-group-ui-test.ts
# Expected: FAIL，组件或 locale key 缺失。
```

- [ ] **Step 3: 实现 hook 和独立请求状态**

`useIncidentIMGroup` 必须维护 `groupLoading/optionsLoading/createLoading/actionLoadingKey/memberLoading`，不得用一个布尔值锁死所有操作。用 `incidentPk + group.id` 校验响应归属；创建短轮询只保留一个 timer，document hidden 时停止，visible/focus 时立即刷新；unmount 时 abort 并 clearTimeout。

```typescript
export interface IncidentIMGroupController {
  group: IncidentIMGroup | null;
  groupLoading: boolean;
  actionLoadingKey: string | null;
  refreshGroup: () => Promise<void>;
  openCreate: () => Promise<void>;
  retry: () => Promise<void>;
  pause: () => Promise<void>;
  resume: () => Promise<void>;
  unlink: (groupName: string) => Promise<void>;
}
```

- [ ] **Step 4: 实现状态卡和动作层级**

卡片固定置于右栏协作者列表上方。直接动作最多三个：查看详情、`deriveIMGroupView().primaryAction`、更多。未建群、局部加载失败、创建中、正常、部分成功、manual pause、incident closed、create failed、degraded 分别有显式文案。使用 `Tag/Button/Dropdown/Skeleton/Tooltip` 和 theme token；不得硬编码 hex 或给页面增加横向滚动。

- [ ] **Step 5: 实现创建 Modal**

Modal 宽 600px，body `maxHeight: calc(100vh - 240px)`。打开前加载 options；切换 channel 时重取预览并重置 owner。全部负责人未映射时禁用提交；部分未映射只显示 warning。提交收到 202 后关闭并进入创建轮询，网络超时先刷新 group 状态再允许用户再次操作。

- [ ] **Step 6: 实现成员 Drawer 与确认弹窗**

Drawer 宽 `min(720px, 100vw)`，默认待处理筛选，分页 20，排序由后端保证。创建中显示四阶段进度而不是空表。暂停确认复述影响；解绑必须输入完整群名才启用 danger 按钮，成功 Toast 明确“原飞书群未删除”。打开群聊只使用后端 `open_chat_url`，否则只提供复制 chat ID。

- [ ] **Step 7: 接入现有协作人流程**

在 `CollaborationTab` 维护 `imGroupRefreshVersion` 数字；邀请或移除成功后同时调用 `onRefresh()` 和 `setImGroupRefreshVersion(value => value + 1)`。`IncidentIMGroupPanel` 接收 `refreshVersion`，变化时调用自身 hook 的 `refreshGroup()`。移除协作者前新增确认弹窗并显示 `removeCollaboratorWarning`，确认后沿用现有 `modifyIncidentDetail`，不得调用任何 IM remove API。

- [ ] **Step 8: 补齐 i18n、运行 GREEN 和前端门禁**

```bash
cd web && pnpm exec tsx scripts/incident-im-group-ui-test.ts
cd web && pnpm lint
cd web && pnpm type-check
```

Expected: 三项 PASS；无新增 `any`、硬编码中文、硬编码状态色或未清理 timer。

- [ ] **Step 9: 提交**

```bash
git add web/src/app/alarm/'(pages)'/incidents/components/collaboration web/src/app/alarm/types/incidents.ts web/src/app/alarm/api/incidents.ts web/src/app/alarm/locales/zh.json web/src/app/alarm/locales/en.json web/scripts/incident-im-group-ui-test.ts web/package.json
git commit -m "feat(web): 增加 Incident 飞书群交互"
```

### Task 11: 全量门禁和真实飞书闭环验证

**Files:**
- Create: `docs/validation/incident-feishu-group-runbook.md`
- Create: `docs/reviews/incident-feishu-group-validation-2026-07-21.md`

**Interfaces:**
- Consumes: Tasks 1-10 的完整功能。
- Produces: 可复现的飞书测试租户运行手册、12 场景证据、发布结论。

- [ ] **Step 1: 编写无凭据的验证 Runbook**

Runbook 必须写明：使用专用测试租户和测试应用；凭据只在系统管理 UI 输入；准备 2 名已映射负责人、1 名已映射协作人、1 名未映射协作人；应用需要建群、查群、增员、群消息和用户可见范围；记录 Incident ID、channel ID、group binding ID、chat ID 脱敏尾号和飞书 request ID；解绑后手工删除测试群完成清理。

- [ ] **Step 2: 运行后端完整门禁**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/system_mgmt/tests/test_feishu_im_group_provider.py apps/system_mgmt/tests/test_im_group_service.py apps/system_mgmt/tests/test_im_notification_viewset.py apps/alerts/tests/test_incident_im_models.py apps/alerts/tests/test_incident_im_members.py apps/alerts/tests/test_incident_im_group_views.py apps/alerts/tests/test_incident_im_delivery.py apps/alerts/tests/test_incident_im_reconcile.py apps/alerts/tests/test_outbox.py apps/alerts/tests/test_incident_operator.py -q
cd server && INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run python manage.py makemigrations --check --dry-run
```

Expected: 全部 PASS；无遗漏迁移。

- [ ] **Step 3: 运行 Web 完整门禁**

```bash
cd web && pnpm exec tsx scripts/incident-im-group-ui-test.ts
cd web && pnpm lint
cd web && pnpm type-check
```

Expected: 全部 PASS。

- [ ] **Step 4: 在测试租户执行 12 个真实场景**

依次验证并记录实际结果：用户同步与预览；单次建群；部分映射；Incident 摘要；重复提交/任务重投；补齐映射自动入群；新增协作人自动入群；移除人员不退群；Incident 关闭/重开；手工暂停/恢复；权限/非法用户/网络失败后重试；解绑保留外部群并允许新绑定。

每项证据必须包含 BK-Lite 页面状态、飞书实际结果和服务端 request ID；截图隐藏手机号、邮箱、外部用户 ID 和凭据。任何重复群、错误成员状态、解绑后继续增员或凭据泄漏都将发布结论标为 Block。

- [ ] **Step 5: 写验证报告**

`docs/reviews/incident-feishu-group-validation-2026-07-21.md` 固定包含：环境摘要、自动化命令与退出码、12 场景结果表、发现问题、残留测试对象、清理结果、最终 `Pass/Conditional Pass/Block`。失败场景不得写成通过，必须关联缺陷编号。

- [ ] **Step 6: 提交验证文档**

```bash
git add docs/validation/incident-feishu-group-runbook.md docs/reviews/incident-feishu-group-validation-2026-07-21.md
git commit -m "test(alerts): 验证 Incident 飞书群闭环"
```

---

## Plan Self-Review

| 规格能力 | 实施任务 | 验收证据 |
|---|---|---|
| 飞书 Provider、渠道权限与账号映射 | Tasks 1-4 | Provider HTTP 合同、渠道可见性、映射冲突和快照测试 |
| 负责人权限、一键建群与异步幂等 | Tasks 5-6 | API 权限/并发测试、Outbox 崩溃边界和部分失败测试 |
| 只增不减、持续同步与生命周期 | Tasks 7-8 | 新增/移除/映射补齐、关闭/重开、暂停/恢复/解绑测试 |
| 前端状态卡、Modal、Drawer 和管理动作 | Tasks 9-10 | 纯状态测试、组件合同、双语 key、lint 和 type-check |
| 测试租户完整闭环 | Task 11 | 12 场景验证表、request ID、清理记录和发布结论 |

与规格相比有三处基于仓库事实的实施收敛：后端路由使用现有 Alerts 前缀 `/api/v1/alerts/api/incident/{id}/im-group/`；人员和生命周期变化在业务事务中持久化 reconcile Outbox，而非只在 `transaction.on_commit` 中触发 broker 调用；前端用父组件 `refreshVersion` 协调 Incident 与群状态刷新，避免暴露子组件 imperative ref。三处均不改变已确认产品语义。

自检结果：11 个任务均包含文件、输入/输出接口、RED/GREEN 命令和提交边界；无占位标记、省略实现或未定义示例 helper；模型 UUID、API string ID、状态枚举、错误码、Outbox kind 和前端字段名称在任务间一致。

---

## Final Verification

- [ ] 确认 `git diff --check` 无输出。
- [ ] 确认 `git status --short` 只包含本计划产生且已明确处理的文件。
- [ ] 确认两个现有 Alerts `0021` 迁移都被 `0022_incident_im_group` 依赖，迁移图无冲突叶子。
- [ ] 确认新 Provider/Alerts 服务覆盖率均达到 75%。
- [ ] 确认系统管理既有单人 IM 通知、用户同步和渠道权限测试保持通过。
- [ ] 确认 Incident 既有创建、更新、关闭、重开和协作人交互保持通过。
- [ ] 确认飞书测试租户没有重复群、遗留自动同步绑定或未清理测试群。
- [ ] 使用 `superpowers:requesting-code-review` 对规格、计划、实现和真实验证证据做最终审阅。
