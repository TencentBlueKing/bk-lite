# IM 应用通知渠道改进实现计划

> **For agentic workers:** REQUIRED EXECUTION STYLE: Use `superpowers:executing-plans` to implement this plan in a single mainline sequence. Follow the task order in this document, use lightweight validation between tasks, and perform full verification/review only after all planned tasks are complete. Steps use checkbox (`- [ ]`) syntax for tracking.
> 
> **Worktree requirement:** Execute this plan inside a fresh git worktree created via `superpowers:using-git-worktrees`. Do not commit or push on the user's behalf. After all tasks are complete, stop and notify the user for review before any commit.

**Goal:** 完成 IM 应用通知渠道的表达优化与组织隔离闭环：列表状态列只展示最近一次同步结果、发送字段增加默认提示、操作列与发送入口重构、补齐 `IMNotificationChannel` 的 team 隔离。

**Architecture:** 后端保持 `channel.status` 作为“是否可发送”的内部状态，新增 `display_sync_status` 等展示字段供前端列表消费；`IMNotificationChannelViewSet` 复用现有 `ChannelViewSet` / `IntegrationInstanceViewSet` 的 team 隔离模式；前端将测试发送上提为统一发送入口，弹窗内选择 channel 及已映射用户；操作列去掉查看映射，同步映射/查看记录文案调整。

**Tech Stack:** Django 4.2, DRF, pytest, Next.js 16, React 19, TypeScript, Ant Design, Tailwind CSS

## Execution Constraints

- The primary objective is to complete all task goals in this plan end-to-end.
- Perform the full verification and review after all planned tasks are completed; do not stop for a separate full review after each individual task.
- Prefer lightweight, directly relevant validation and review first; avoid spending disproportionate effort on heavyweight verification unless risk or uncertainty justifies it.
- Do not force through ambiguous issues. If design intent, provider contract semantics, or implementation direction becomes unclear, stop and align with the user before continuing.
- Follow existing repository code style and implementation patterns.
- Keep changes tightly scoped to the IM notification channel improvements; avoid unrelated refactors, opportunistic cleanup, or broad restructuring.
- Treat task completion as behaviorally meeting the planned end-state, not merely landing partial code or passing isolated interim tests.
- Prefer no temporary compatibility layer unless explicitly required.
- Execute this plan in `executing-plans` style: follow the documented task order in a single mainline flow, avoid large parallel workstreams, and use only lightweight interim validation until final verification.
- **Do not commit or push any changes.** After the final verification task is complete, stop and notify the user for review. Commits happen only after explicit user approval.

---

## File Structure

### Existing files to modify

- `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`
  - Add team isolation helpers and wire them into `list/retrieve/create/update/destroy` and all actions.
  - Add new `send` action as the generic send entry point.

- `server/apps/system_mgmt/serializers/im_notification_channel_serializer.py`
  - Add `display_sync_status` and `display_sync_summary` SerializerMethodFields.
  - Keep `channel.status` in the response for send-button readiness checks.

- `server/apps/system_mgmt/services/im_notification_service.py`
  - Add `send_im_notification_to_users(channel_id, user_ids, title, content)` helper reused by the new send action.

- `server/apps/system_mgmt/tests/test_im_notification_viewset.py`
  - Add tests for team isolation, display fields, and the new send action.

- `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`
  - Merge list status column into "最近同步".
  - Move refresh/send buttons to top-right, reorder as 添加 | 发送 | 刷新.
  - Remove "查看映射" button and mappings drawer.
  - Rename "同步映射" → "手动同步", "查看记录" → "同步记录".
  - Add unified send modal with channel select and user multi-select.
  - Add bottom hint under receive field in add/edit modal.

- `web/src/app/system-manager/api/im-notification/index.ts`
  - Add `sendNotification` API call for the new generic send endpoint.

- `web/src/app/system-manager/utils/imNotificationUtils.ts`
  - Extend `getSyncRunStatusColor` / `getSyncRunStatusText` to support `never_synced`.

- `web/src/app/system-manager/locales/zh.json`
  - Add/ update keys for send modal, button renames, receive field hint, `never_synced` status.

- `web/src/app/system-manager/locales/en.json`
  - Same as above for English.

### Existing files likely to stay outside changes

- `server/apps/system_mgmt/models/im_notification_channel.py`
  Model already has the needed `team` field; no migration required.

- `web/src/app/system-manager/components/channel/channelModal.tsx`
  Not used by the IM notification page; changes are localized to `im-notification/page.tsx`.

### Reference files to read during implementation

- `docs/superpowers/specs/2026-06-24-im-notification-channel-design.md`
- `server/apps/system_mgmt/viewset/channel_viewset.py`
- `server/apps/system_mgmt/viewset/integration_instance_viewset.py`
- `web/src/app/system-manager/(pages)/user/login-auth/page.tsx` (for refresh button style)

---

### Task 1: Backend team isolation for IMNotificationChannelViewSet

**Files:**
- Modify: `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_viewset.py`

- [ ] **Step 1: Add team isolation helpers to the viewset**

Insert the following private methods into `IMNotificationChannelViewSet` (place them near the top, after `ordering`):

```python
    def _get_user_group_ids(self, user):
        if getattr(user, "is_superuser", False):
            return None
        return {g["id"] for g in getattr(user, "group_list", [])}

    def _filter_by_accessible_teams(self, queryset, user):
        if getattr(user, "is_superuser", False):
            return queryset

        user_group_ids = self._get_user_group_ids(user)
        if not user_group_ids:
            return queryset.none()

        query = None
        for group_id in user_group_ids:
            condition = Q(team__contains=group_id)
            query = condition if query is None else query | condition
        return queryset.filter(query) if query is not None else queryset

    def _validate_channel_permission(self, request, channel):
        if getattr(request.user, "is_superuser", False):
            return True, None

        user_group_ids = self._get_user_group_ids(request.user)
        channel_team_ids = set(channel.team or [])

        if not user_group_ids or not user_group_ids.intersection(channel_team_ids):
            message = self.loader.get("error.no_permission_access_team", "无权访问该团队数据") if self.loader else "无权访问该团队数据"
            return False, JsonResponse({"result": False, "message": message}, status=403)
        return True, None

    def _validate_team_in_user_scope(self, request, team_values):
        if getattr(request.user, "is_superuser", False):
            return True, None

        user_group_ids = self._get_user_group_ids(request.user)
        if not user_group_ids:
            return False, JsonResponse({"result": False, "message": "无权访问该团队数据"}, status=403)

        normalized = []
        if isinstance(team_values, (int, str)):
            team_values = [team_values]
        for value in team_values or []:
            try:
                normalized.append(int(value))
            except (TypeError, ValueError):
                continue

        invalid = set(normalized) - user_group_ids
        if invalid:
            message = self.loader.get("error.no_permission_for_groups", "您没有以下组织的权限") if self.loader else "您没有以下组织的权限"
            return False, JsonResponse({"result": False, "message": message}, status=403)
        return True, None
```

Also add the `Q` import at the top of the file:

```python
from django.db.models import Q
```

- [ ] **Step 2: Wire team filtering into list**

Replace the existing `list` method with:

```python
    @HasPermission("channel_list-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = self._filter_by_accessible_teams(queryset, request.user)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
```

- [ ] **Step 3: Wire team permission checks into retrieve/update/destroy and all actions**

Replace `retrieve`:

```python
    @HasPermission("channel_list-View")
    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        is_valid, error_response = self._validate_channel_permission(request, obj)
        if not is_valid:
            return error_response
        serializer = self.get_serializer(obj)
        return Response(serializer.data)
```

Replace `update`:

```python
    @HasPermission("channel_list-Edit")
    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        is_valid, error_response = self._validate_channel_permission(request, obj)
        if not is_valid:
            return error_response

        team_values = request.data.get("team") or getattr(obj, "team", None)
        is_valid, error_response = self._validate_team_in_user_scope(request, team_values)
        if not is_valid:
            return error_response

        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            log_operation(request, "update", "channel", f"编辑IM应用通知: {response.data.get('name', '')}")
        return response
```

Replace `destroy`:

```python
    @HasPermission("channel_list-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        is_valid, error_response = self._validate_channel_permission(request, obj)
        if not is_valid:
            return error_response

        channel_name = obj.name
        obj.delete_sync_periodic_task()
        response = super().destroy(request, *args, **kwargs)
        if response.status_code == 200:
            log_operation(request, "delete", "channel", f"删除IM应用通知: {channel_name}")
        return response
```

For each action, add the permission check at the top. Example for `sync_mappings`:

```python
    @action(methods=["POST"], detail=True)
    @HasPermission("channel_list-Edit")
    def sync_mappings(self, request, *args, **kwargs):
        channel = self.get_object()
        is_valid, error_response = self._validate_channel_permission(request, channel)
        if not is_valid:
            return error_response
        result = create_im_notification_sync_run(channel.id)
        if not result.get("result"):
            return JsonResponse(result, status=400)
        run_id = result["data"]["run_id"]
        execute_im_notification_sync_run_task.delay(run_id)
        return JsonResponse(result, status=200)
```

Apply the same pattern to `mappings`, `records`, and `test_send`.

For `create`, add team scope validation:

```python
    @HasPermission("channel_list-Add")
    def create(self, request, *args, **kwargs):
        team_values = request.data.get("team")
        is_valid, error_response = self._validate_team_in_user_scope(request, team_values)
        if not is_valid:
            return error_response

        response = super().create(request, *args, **kwargs)
        if response.status_code == 201:
            log_operation(request, "create", "channel", f"新增IM应用通知: {response.data.get('name', '')}")
        return response
```

- [ ] **Step 4: Write failing tests for team isolation**

Append to `server/apps/system_mgmt/tests/test_im_notification_viewset.py`:

```python
@pytest.mark.django_db
def test_list_filters_channels_by_team(api_client, authenticated_user, ready_im_instance):
    authenticated_user.group_list = [{"id": 1, "name": "Team A"}]
    authenticated_user.save(update_fields=["group_list"])
    authenticated_user.permission = {"system-manager": {"channel_list-View"}}
    authenticated_user.save(update_fields=["permission"])

    IMNotificationChannel.objects.create(
        name="visible-channel",
        integration_instance=ready_im_instance,
        enabled=True,
        status="pending_sync",
        platform_match_field="email",
        external_match_field="email",
        external_receive_field="user_id",
        team=[1],
    )
    IMNotificationChannel.objects.create(
        name="hidden-channel",
        integration_instance=ready_im_instance,
        enabled=True,
        status="pending_sync",
        platform_match_field="email",
        external_match_field="email",
        external_receive_field="user_id",
        team=[2],
    )

    response = api_client.get("/api/v1/system_mgmt/im_notification_channel/", {"page": 1, "page_size": 10})

    assert response.status_code == 200
    names = {item["name"] for item in response.data["items"]}
    assert "visible-channel" in names
    assert "hidden-channel" not in names


@pytest.mark.django_db
def test_retrieve_rejects_channel_outside_user_team(api_client, authenticated_user, channel):
    authenticated_user.group_list = [{"id": 999, "name": "Other Team"}]
    authenticated_user.permission = {"system-manager": {"channel_list-View"}}
    authenticated_user.save(update_fields=["group_list", "permission"])

    response = api_client.get(f"/api/v1/system_mgmt/im_notification_channel/{channel.id}/")

    assert response.status_code == 403
```

- [ ] **Step 5: Run the new team isolation tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_im_notification_viewset.py::test_list_filters_channels_by_team apps/system_mgmt/tests/test_im_notification_viewset.py::test_retrieve_rejects_channel_outside_user_team -v
```

Expected: PASS after implementation is complete; if run before implementation, FAIL.

- [ ] **Step 6: Commit**

```bash
git add server/apps/system_mgmt/viewset/im_notification_channel_viewset.py server/apps/system_mgmt/tests/test_im_notification_viewset.py
git commit -m "feat(system_mgmt): add team isolation to IM notification channel viewset

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Backend display fields for list status column

**Files:**
- Modify: `server/apps/system_mgmt/serializers/im_notification_channel_serializer.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_viewset.py`

- [ ] **Step 1: Add display_sync_status and display_sync_summary fields**

In `IMNotificationChannelSerializer`, add to the `Meta` field list (or keep `fields = "__all__"` and just add the methods):

```python
    display_sync_status = serializers.SerializerMethodField()
    display_sync_summary = serializers.SerializerMethodField()
```

Add the getter methods:

```python
    def get_display_sync_status(self, obj):
        latest_run = self._get_latest_run(obj)
        if latest_run and latest_run.status == im_notification_service.SYNC_RUN_STATUS_RUNNING:
            return "running"
        if latest_run:
            return latest_run.status
        return "never_synced"

    def get_display_sync_summary(self, obj):
        latest_run = self._get_latest_run(obj)
        return latest_run.summary if latest_run else ""
```

- [ ] **Step 2: Update existing tests that assert display_status**

The existing test `test_channel_serializer_returns_display_status_from_channel_and_latest_run` asserts on `display_status`. Keep `display_status` behavior unchanged for backward compatibility, and add assertions for the new fields.

Replace that test with:

```python
@pytest.mark.django_db
def test_channel_serializer_returns_display_status_and_display_sync_status(channel):
    IMNotificationSyncRun.objects.create(
        channel=channel,
        status="running",
        summary="syncing",
        started_at=timezone.now(),
        locked_config_snapshot={},
    )

    data = IMNotificationChannelSerializer(channel).data

    assert data["display_status"] == "syncing"
    assert data["display_sync_status"] == "running"
    assert data["latest_sync_status"] == "running"
    assert data["status"] == "pending_sync"
```

- [ ] **Step 3: Add test for never_synced and partial statuses**

Append:

```python
@pytest.mark.django_db
def test_channel_serializer_returns_never_synced_when_no_run(channel):
    data = IMNotificationChannelSerializer(channel).data
    assert data["display_sync_status"] == "never_synced"
    assert data["display_sync_summary"] == ""


@pytest.mark.django_db
def test_channel_serializer_returns_partial_when_latest_run_partial(channel):
    IMNotificationSyncRun.objects.create(
        channel=channel,
        status="partial",
        summary="Matched 5 of 10 external users",
        started_at=timezone.now(),
        locked_config_snapshot={},
    )
    data = IMNotificationChannelSerializer(channel).data
    assert data["display_sync_status"] == "partial"
    assert data["display_sync_summary"] == "Matched 5 of 10 external users"
```

- [ ] **Step 4: Run serializer tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_im_notification_viewset.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/apps/system_mgmt/serializers/im_notification_channel_serializer.py server/apps/system_mgmt/tests/test_im_notification_viewset.py
git commit -m "feat(system_mgmt): add display_sync_status and display_sync_summary to IM notification serializer

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Backend generic send action

**Files:**
- Modify: `server/apps/system_mgmt/services/im_notification_service.py`
- Modify: `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_viewset.py`

- [ ] **Step 1: Add send helper to service layer**

Append to `server/apps/system_mgmt/services/im_notification_service.py`:

```python
def send_im_notification_to_users(channel_id: int, user_ids: list[int], title: str, content: str):
    channel = IMNotificationChannel.objects.select_related("integration_instance").filter(id=channel_id, enabled=True).first()
    if not channel:
        return {"result": False, "message": "IM notification channel not found"}
    if channel.status != CHANNEL_STATUS_READY:
        return {"result": False, "message": "IM notification channel requires a successful sync before sending"}

    if not user_ids:
        return {"result": False, "message": "No recipients selected"}

    mappings = IMNotificationUserMapping.objects.filter(channel=channel, user_id__in=user_ids)
    receive_ids = []
    for mapping in mappings:
        receive_id = str((mapping.external_snapshot or {}).get(mapping.external_receive_key) or "").strip()
        if receive_id:
            receive_ids.append(receive_id)

    if not receive_ids:
        return {"result": False, "message": "No matched IM recipients found for selected users"}

    runtime_service = RuntimeApplicationService()
    result = runtime_service.execute(
        provider_key=channel.integration_instance.provider_key,
        capability_key="im_notification",
        operation="send_message",
        config=channel.integration_instance.get_runtime_config(),
        title=title,
        content=content,
        receive_id_type=channel.external_receive_field,
        receive_ids=receive_ids,
    )
    return {"result": result.success, "message": result.summary, "data": result.to_dict()}
```

- [ ] **Step 2: Add send action to viewset**

In `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`, add the import:

```python
from apps.system_mgmt.services.im_notification_service import create_im_notification_sync_run, send_im_notification, send_im_notification_to_users
```

Add the action:

```python
    @action(methods=["POST"], detail=False)
    @HasPermission("channel_list-Edit")
    def send(self, request, *args, **kwargs):
        channel_id = request.data.get("channel_id")
        user_ids = request.data.get("user_ids") or []
        title = request.data.get("title", "")
        content = request.data.get("content", "")

        try:
            channel_id = int(channel_id)
            user_ids = [int(uid) for uid in user_ids]
        except (TypeError, ValueError):
            return JsonResponse({"result": False, "message": "Invalid channel_id or user_ids"}, status=400)

        channel = IMNotificationChannel.objects.filter(id=channel_id).first()
        if not channel:
            return JsonResponse({"result": False, "message": "IM notification channel not found"}, status=404)

        is_valid, error_response = self._validate_channel_permission(request, channel)
        if not is_valid:
            return error_response

        result = send_im_notification_to_users(channel_id, user_ids, title, content)
        status = 200 if result.get("result") else 400
        return JsonResponse(result, status=status)
```

- [ ] **Step 3: Add tests for the new send action**

Append:

```python
@pytest.mark.django_db
@patch("apps.system_mgmt.services.im_notification_service.RuntimeApplicationService")
def test_send_action_dispatches_to_provider(mock_runtime_class, api_client, authenticated_user, channel, ready_im_instance):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"channel_list-Edit"}}
    authenticated_user.save(update_fields=["is_superuser", "permission"])

    channel.status = "ready"
    channel.save(update_fields=["status"])

    from apps.base.models import User
    user = User.objects.create_user(
        username="receiver",
        password="testpass123",
        domain="domain.com",
        email="receiver@example.com",
    )
    IMNotificationUserMapping.objects.create(
        channel=channel,
        user=user,
        external_identity_key="user_id",
        external_identity_value="u123",
        external_receive_key="user_id",
        external_snapshot={"user_id": "u123"},
    )

    mock_runtime = mock_runtime_class.return_value
    mock_runtime.execute.return_value = MagicMock(success=True, summary="sent", to_dict=lambda: {"ok": True})

    response = api_client.post(
        "/api/v1/system_mgmt/im_notification_channel/send/",
        {"channel_id": channel.id, "user_ids": [user.id], "title": "Hello", "content": "World"},
    )

    assert response.status_code == 200
    assert response.json()["result"] is True


@pytest.mark.django_db
def test_send_action_rejects_channel_not_ready(api_client, authenticated_user, channel):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"channel_list-Edit"}}
    authenticated_user.save(update_fields=["is_superuser", "permission"])

    response = api_client.post(
        "/api/v1/system_mgmt/im_notification_channel/send/",
        {"channel_id": channel.id, "user_ids": [], "title": "Hello", "content": "World"},
    )

    assert response.status_code == 400
    assert "requires a successful sync" in response.json()["message"]
```

Add the `MagicMock` import at the top of the test file:

```python
from unittest.mock import MagicMock, patch
```

- [ ] **Step 4: Run send action tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_im_notification_viewset.py::test_send_action_dispatches_to_provider apps/system_mgmt/tests/test_im_notification_viewset.py::test_send_action_rejects_channel_not_ready -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/apps/system_mgmt/services/im_notification_service.py server/apps/system_mgmt/viewset/im_notification_channel_viewset.py server/apps/system_mgmt/tests/test_im_notification_viewset.py
git commit -m "feat(system_mgmt): add generic send action for IM notification channels

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: Frontend utilities and i18n updates

**Files:**
- Modify: `web/src/app/system-manager/utils/imNotificationUtils.ts`
- Modify: `web/src/app/system-manager/locales/zh.json`
- Modify: `web/src/app/system-manager/locales/en.json`
- Modify: `web/src/app/system-manager/api/im-notification/index.ts`

- [ ] **Step 1: Extend status helpers**

Update `web/src/app/system-manager/utils/imNotificationUtils.ts`:

```typescript
export function getSyncRunStatusColor(status: string): string {
  const map: Record<string, string> = {
    running: 'processing',
    success: 'success',
    partial: 'warning',
    failed: 'error',
    never_synced: 'default',
  };
  return map[status] ?? 'default';
}

export function getSyncRunStatusText(
  status: string,
  t: (key: string, fallback?: string) => string,
): string {
  return t(`system.channel.imNotificationPage.syncRunStatus.${status || 'never_synced'}`);
}
```

- [ ] **Step 2: Add API method for generic send**

In `web/src/app/system-manager/api/im-notification/index.ts`, add:

```typescript
  async function sendNotification(payload: {
    channel_id: number;
    user_ids: number[];
    title: string;
    content: string;
  }): Promise<Record<string, unknown> | undefined> {
    return await post('/system_mgmt/im_notification_channel/send/', payload);
  }
```

And add `sendNotification` to the returned object.

- [ ] **Step 3: Update locale keys**

In `web/src/app/system-manager/locales/zh.json`, inside `imNotificationPage`:

- Update `syncMappings` to `"手动同步"`.
- Update `viewRecords` to `"同步记录"`.
- Update `syncRunStatus` to include `never_synced`:

```json
"syncRunStatus": {
  "running": "同步中",
  "success": "成功",
  "partial": "部分成功",
  "failed": "失败",
  "never_synced": "待同步"
}
```

- Add `receiveFieldHint`:

```json
"receiveFieldHint": "用于将消息发送到指定用户的凭证，若无其它需求，保持默认即可。"
```

- Add send modal keys (add near the end of `imNotificationPage`):

```json
"sendTitle": "发送消息",
"sendChannel": "IM 同步项",
"sendChannelPlaceholder": "请选择 IM 同步项",
"sendReceivers": "接收人",
"sendReceiversPlaceholder": "请选择接收人",
"sendMessageTitle": "标题",
"sendMessageContent": "内容",
"sendSuccess": "发送成功",
"sendFailed": "发送失败"
```

- Add refresh key if not present under `common`:

```json
"refresh": "刷新"
```

Apply the same additions/changes to `web/src/app/system-manager/locales/en.json` with English translations.

- [ ] **Step 4: Run lint on touched utility/api files**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/utils/imNotificationUtils.ts src/app/system-manager/api/im-notification/index.ts
```

Expected: no new lint errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/system-manager/utils/imNotificationUtils.ts web/src/app/system-manager/api/im-notification/index.ts web/src/app/system-manager/locales/zh.json web/src/app/system-manager/locales/en.json
git commit -m "feat(web): extend IM notification utils, API, and i18n for status and send modal

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: Frontend list page layout and columns

**Files:**
- Modify: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`

- [ ] **Step 1: Add ReloadOutlined import and refresh state**

Add to imports:

```typescript
import { ArrowLeftOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
```

Add state:

```typescript
const [refreshing, setRefreshing] = useState(false);
```

- [ ] **Step 2: Add refresh handler**

Add function:

```typescript
const handleRefresh = async () => {
  setRefreshing(true);
  try {
    await fetchChannels(pagination.current, pagination.pageSize);
  } finally {
    setRefreshing(false);
  }
};
```

- [ ] **Step 3: Reorder top-right buttons and move send/refresh**

Update `rightSection` header area. Replace the existing button group with:

```tsx
<div className="mb-4 flex items-center justify-between gap-2">
  <div className="flex items-center">
    <Button color="default" variant="link" icon={<ArrowLeftOutlined />} onClick={handleBack} />
  </div>
  <div className="flex items-center gap-2">
    <Input.Search
      placeholder={t('system.channel.imNotificationPage.search')}
      allowClear
      style={{ width: 280 }}
      onSearch={setSearchText}
      onChange={(event) => !event.target.value && setSearchText('')}
    />
    <PermissionWrapper requiredPermissions={['Add']}>
      <Button type="primary" icon={<PlusOutlined />} onClick={() => openModal(null)}>
        {t('common.add')}
      </Button>
    </PermissionWrapper>
    <PermissionWrapper requiredPermissions={['Edit']}>
      <Button onClick={() => setSendOpen(true)}>
        {t('system.channel.imNotificationPage.sendTitle')}
      </Button>
    </PermissionWrapper>
    <Button type="text" icon={<ReloadOutlined />} onClick={handleRefresh} loading={refreshing} />
  </div>
</div>
```

Add state for send modal:

```typescript
const [sendOpen, setSendOpen] = useState(false);
```

- [ ] **Step 4: Replace list columns**

Remove the old `display_status` column and the old `latest_sync` column. Replace with a single merged `latest_sync` column:

```tsx
const columns: ColumnItem[] = [
  {
    key: 'name',
    title: t('system.channel.imNotificationPage.name'),
    dataIndex: 'name',
  },
  {
    key: 'integration_instance_name',
    title: t('system.channel.imNotificationPage.integrationInstance'),
    dataIndex: 'integration_instance_name',
  },
  {
    key: 'latest_sync',
    title: t('system.channel.imNotificationPage.latestSync'),
    dataIndex: 'display_sync_status',
    render: (_, record: IMNotificationChannel) => {
      const status = record.display_sync_status;
      if (status === 'never_synced' || !status) {
        return <span>{t('system.channel.imNotificationPage.latestSyncEmpty')}</span>;
      }

      const latestSyncTime = record.latest_sync_finished_at || record.latest_sync_started_at;
      const summary = record.display_sync_summary || record.latest_sync_summary;

      return (
        <div className="leading-6">
          <div className="flex items-center gap-2">
            <Tag color={getSyncRunStatusColor(status)}>
              {getSyncRunStatusText(status, t)}
            </Tag>
            <span className="text-base font-semibold text-[var(--color-text-1)]">
              {latestSyncTime ? renderTime(latestSyncTime) : '--'}
            </span>
          </div>
          {summary ? (
            <div className="text-xs text-[var(--color-text-3)]">{summary}</div>
          ) : null}
        </div>
      );
    },
    width: 260,
  },
  {
    key: 'sync_period',
    title: t('system.channel.imNotificationPage.syncPeriod'),
    dataIndex: 'schedule_config',
    render: (_, record: IMNotificationChannel) => renderSyncPeriod(record, t),
    width: 220,
  },
  {
    key: 'enabled',
    title: t('system.channel.imNotificationPage.enabledColumn'),
    dataIndex: 'enabled',
    width: 80,
    render: (enabled: boolean, record: IMNotificationChannel) => (
      <Switch size="small" checked={enabled} onChange={(checked) => handleToggleEnabled(record, checked)} />
    ),
  },
  {
    title: t('common.actions'),
    key: 'actions',
    dataIndex: 'actions',
    fixed: 'right',
    width: 220,
    render: (_, record: IMNotificationChannel) => (
      <Space wrap>
        <PermissionWrapper requiredPermissions={['Edit']}>
          <Button type="link" size="small" onClick={() => openModal(record)}>
            {t('common.edit')}
          </Button>
        </PermissionWrapper>
        <PermissionWrapper requiredPermissions={['Edit']}>
          <Button
            type="link"
            size="small"
            onClick={() => handleSyncMappings(record)}
            disabled={isChannelSyncRunning(record.latest_sync_status)}
          >
            {t('system.channel.imNotificationPage.syncMappings')}
          </Button>
        </PermissionWrapper>
        <Button type="link" size="small" onClick={() => handleViewRecords(record)}>
          {t('system.channel.imNotificationPage.viewRecords')}
        </Button>
        <PermissionWrapper requiredPermissions={['Delete']}>
          <Popconfirm
            title={t('system.channel.imNotificationPage.deleteConfirm')}
            onConfirm={() => handleDelete(record)}
          >
            <Button type="link" size="small" danger>
              {t('common.delete')}
            </Button>
          </Popconfirm>
        </PermissionWrapper>
      </Space>
    ),
  },
];
```

- [ ] **Step 5: Remove mappings drawer and related state**

Remove state:

```typescript
// Remove these
const [mappingsOpen, setMappingsOpen] = useState(false);
const [mappingsChannel, setMappingsChannel] = useState<IMNotificationChannel | null>(null);
const [mappings, setMappings] = useState<IMNotificationUserMapping[]>([]);
const [mappingsLoading, setMappingsLoading] = useState(false);
const [mapPagination, setMapPagination] = useState<PaginationState>({...});
```

Remove `getMappings`, `fetchMappings`, `handleViewMappings`, and `mappingColumns`.

Remove the mappings `<Drawer />` JSX.

- [ ] **Step 6: Remove per-row test_send button and old test modal state**

Remove state:

```typescript
// Remove these
const [testForm] = Form.useForm();
const [testOpen, setTestOpen] = useState(false);
const [testLoading, setTestLoading] = useState(false);
const [testChannel, setTestChannel] = useState<IMNotificationChannel | null>(null);
```

Remove `handleTestSend`, `handleTestSendOk`, and the test send `<OperateModal />` JSX.

- [ ] **Step 7: Run lint on the page**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/\(pages\)/channel/im-notification/page.tsx
```

Expected: no new lint errors.

- [ ] **Step 8: Commit**

```bash
git add web/src/app/system-manager/(pages)/channel/im-notification/page.tsx
git commit -m "feat(web): refactor IM notification list columns, top buttons, and remove mappings drawer

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: Frontend unified send modal

**Files:**
- Modify: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`
- Modify: `web/src/app/system-manager/types/im-notification.ts` (if type adjustments are needed)

- [ ] **Step 1: Add send modal state and form**

Add state and form after existing form declarations:

```typescript
const [sendForm] = Form.useForm();
const [sendOpen, setSendOpen] = useState(false);
const [sendLoading, setSendLoading] = useState(false);
const [sendChannelId, setSendChannelId] = useState<number | undefined>();
const [sendMappings, setSendMappings] = useState<IMNotificationUserMapping[]>([]);
const [sendMappingsLoading, setSendMappingsLoading] = useState(false);
```

Make sure `sendNotification` and `getMappings` are destructured from `useImNotificationApi`.

- [ ] **Step 2: Add send modal handlers**

Add functions:

```typescript
const handleSendOpen = () => {
  sendForm.resetFields();
  setSendChannelId(undefined);
  setSendMappings([]);
  setSendOpen(true);
};

const handleSendChannelChange = async (channelId: number) => {
  setSendChannelId(channelId);
  sendForm.setFieldsValue({ user_ids: [] });
  setSendMappings([]);
  if (!channelId) return;

  setSendMappingsLoading(true);
  try {
    const { items } = await getMappings(channelId, { page: 1, page_size: 1000 });
    setSendMappings(items ?? []);
  } catch {
    message.error(t('common.fetchFailed'));
    setSendMappings([]);
  } finally {
    setSendMappingsLoading(false);
  }
};

const handleSendOk = async () => {
  try {
    const values = await sendForm.validateFields();
    setSendLoading(true);
    await sendNotification({
      channel_id: values.channel_id,
      user_ids: values.user_ids ?? [],
      title: values.title,
      content: values.content,
    });
    message.success(t('system.channel.imNotificationPage.sendSuccess'));
    setSendOpen(false);
  } catch (error) {
    if (error && typeof error === 'object' && 'errorFields' in error) return;
    message.error(error instanceof Error ? error.message : t('system.channel.imNotificationPage.sendFailed'));
  } finally {
    setSendLoading(false);
  }
};
```

- [ ] **Step 3: Compute send modal options**

Add memoized options:

```typescript
const sendChannelOptions = useMemo(
  () =>
    channels
      .filter((channel) => channel.status === 'ready')
      .map((channel) => ({
        value: channel.id,
        label: `${channel.name} (${channel.integration_instance_name})`,
      })),
  [channels],
);

const sendReceiverOptions = useMemo(
  () =>
    sendMappings.map((mapping) => ({
      value: mapping.user_id,
      label: `${mapping.username} — ${mapping.external_identity_key}: ${mapping.external_identity_value}`,
    })),
  [sendMappings],
);
```

- [ ] **Step 4: Add send modal JSX**

Add the modal near the other modals:

```tsx
<OperateModal
  title={t('system.channel.imNotificationPage.sendTitle')}
  open={sendOpen}
  onOk={handleSendOk}
  onCancel={() => !sendLoading && setSendOpen(false)}
  confirmLoading={sendLoading}
  width={520}
>
  <Form form={sendForm} layout="vertical">
    <Form.Item
      name="channel_id"
      label={t('system.channel.imNotificationPage.sendChannel')}
      rules={[{ required: true }]}
    >
      <Select
        placeholder={t('system.channel.imNotificationPage.sendChannelPlaceholder')}
        options={sendChannelOptions}
        onChange={handleSendChannelChange}
      />
    </Form.Item>
    <Form.Item
      name="user_ids"
      label={t('system.channel.imNotificationPage.sendReceivers')}
      rules={[{ required: true }]}
    >
      <Select
        mode="multiple"
        placeholder={t('system.channel.imNotificationPage.sendReceiversPlaceholder')}
        options={sendReceiverOptions}
        loading={sendMappingsLoading}
        disabled={!sendChannelId}
      />
    </Form.Item>
    <Form.Item
      name="title"
      label={t('system.channel.imNotificationPage.sendMessageTitle')}
      rules={[{ required: true }]}
    >
      <Input />
    </Form.Item>
    <Form.Item
      name="content"
      label={t('system.channel.imNotificationPage.sendMessageContent')}
      rules={[{ required: true }]}
    >
      <Input.TextArea rows={4} />
    </Form.Item>
  </Form>
</OperateModal>
```

- [ ] **Step 5: Update top send button to open the new modal**

Replace the send button click:

```tsx
<PermissionWrapper requiredPermissions={['Edit']}>
  <Button onClick={handleSendOpen}>
    {t('system.channel.imNotificationPage.sendTitle')}
  </Button>
</PermissionWrapper>
```

- [ ] **Step 6: Run lint and type-check**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/\(pages\)/channel/im-notification/page.tsx
pnpm exec tsc -p tsconfig.lint.json --noEmit
```

Expected: no new errors in touched files.

- [ ] **Step 7: Commit**

```bash
git add web/src/app/system-manager/(pages)/channel/im-notification/page.tsx
git commit -m "feat(web): add unified send modal for IM notification channels

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: Add receive field hint in add/edit modal

**Files:**
- Modify: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`

- [ ] **Step 1: Add bottom hint under external_receive_field**

In the add/edit modal, locate the `external_receive_field` Form.Item. Add the hint div after the closing `</Form.Item>`:

```tsx
<Form.Item
  name="external_receive_field"
  label={t('system.channel.imNotificationPage.receiveField')}
  rules={[{ required: true }]}
  className="mb-0"
>
  <Select
    options={externalReceiveOptions}
    disabled={externalReceiveOptions.length === 0}
    placeholder={t('system.channel.imNotificationPage.externalReceiveFieldPlaceholder')}
  />
</Form.Item>
<div className="mt-3 text-[12px] text-[var(--color-text-3)]">
  {t('system.channel.imNotificationPage.receiveFieldHint')}
</div>
```

- [ ] **Step 2: Run lint**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/\(pages\)/channel/im-notification/page.tsx
```

Expected: no new lint errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/system-manager/(pages)/channel/im-notification/page.tsx
git commit -m "feat(web): add receive field hint in IM notification channel modal

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: Final verification and review

**Files:**
- Review: `docs/superpowers/specs/2026-06-24-im-notification-channel-design.md`
- Test: touched backend files
- Test: touched frontend files

- [ ] **Step 1: Run backend tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_im_notification_viewset.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend lint and type-check**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/\(pages\)/channel/im-notification/page.tsx src/app/system-manager/utils/imNotificationUtils.ts src/app/system-manager/api/im-notification/index.ts
pnpm exec tsc -p tsconfig.lint.json --noEmit
```

Expected: touched files clean; if unrelated baseline type issues exist, record them clearly.

- [ ] **Step 3: Manual end-state verification**

Checklist:
- IM 通知列表显示 6 列：名称 / 集成实例 / 最近同步 / 同步周期 / 已启用 / 操作。
- “最近同步”列展示状态标签 + 时间 + 摘要，从未同步时显示“待同步”。
- 操作列包含：编辑 / 手动同步 / 同步记录 / 删除。
- 顶部按钮顺序：添加 / 发送 / 刷新；刷新为 `text` + `ReloadOutlined` 风格。
- 点击“发送”打开统一弹窗：选择 IM 同步项 → 多选已映射用户 → 标题/内容 → 发送。
- 添加/编辑弹窗中发送字段下方显示提示文案。
- 非 superuser 只能看到所属 team 的频道，越权访问返回 403。

- [ ] **Step 4: Review implementation against the spec**

Checklist:
- `channel.status` still controls send readiness; `display_sync_status` is only for display.
- Team isolation covers list/retrieve/create/update/destroy and all actions.
- Generic send action validates channel permission and readiness.
- No changes to `available_instances` global logic.
- i18n keys added for both zh and en.

---

## Self-Review Checklist

- [ ] **Spec coverage:** Every requirement in `2026-06-24-im-notification-channel-design.md` is mapped to a task.
- [ ] **Placeholder scan:** No TBD/TODO/vague steps remain.
- [ ] **Type consistency:** `display_sync_status`, `sendNotification`, `send_im_notification_to_users` signatures match across frontend and backend.
