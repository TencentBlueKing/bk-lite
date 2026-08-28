# 组织归档 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在系统管理中实现组织软删除（归档）、恢复与永久删除，并收敛所有活动组织投影与 UserSyncSource 同步语义。

**Architecture:** 以 `ArchiveService` 集中归档生命周期（锁、校验、写状态、on_commit 副作用）；以活动组织查询入口（`is_delete=False`）收敛 `GroupUtils`、NATS、`current_team`、用户校验；同步对账改为归档，子树与根均按 `sync_source + scoped external_id` 复用原 ID。规格见 `specs/changes/organization-archive/spec.md`。

**Tech Stack:** Django ORM、DRF ViewSet actions、NATS RPC、pytest + PostgreSQL、Next.js / Ant Design、现有 i18n yaml。

## Global Constraints

- 只改任务范围；不触碰工作区无关的 `enterprise`、`web/next-env.d.ts`、`web/tsconfig.json`（本隔离 worktree 应本就不含那些脏改动）。
- `Group` 仅新增 `is_delete = BooleanField(default=False, db_index=True)`；不改 `(name, parent_id)` 唯一约束。
- 归档保留用户 `group_list`；活动投影不得展示归档组织。
- 不改 LoginModule / `tasks._sync_groups` 旧路径。
- 权限点复用 `user_group-Delete Group`。
- 锁顺序：`UserSyncSource`（若有）→ `Group`（按 id）→ `User`（按 id）；缓存清理与操作日志在 `transaction.on_commit`。
- 测试用开发 `.env` 的 PostgreSQL；逻辑库名建议 `bklite_org_archive` → pytest 库 `test_bklite_org_archive`；干净库用 `--create-db`。
- 中文提交信息；代码标识符跟现有风格。

## File Structure

| 文件 | 职责 |
|---|---|
| `server/apps/system_mgmt/models/user.py` | `Group.is_delete` |
| `server/apps/system_mgmt/migrations/0047_group_is_delete.py` | 迁移（编号以当时最新+1为准） |
| `server/apps/system_mgmt/services/group_archive_service.py` | **新建** ArchiveService：归档根判定、列表 capability、归档/恢复/永久删除、锁与用户校验 |
| `server/apps/system_mgmt/utils/group_utils.py` | 活动组织过滤纳入子树/授权查询 |
| `server/apps/system_mgmt/utils/active_group_query.py` | **新建（可选若 GroupUtils 已够）** 统一 `active_groups()` queryset |
| `server/apps/system_mgmt/viewset/group_viewset.py` | `delete_groups`→归档；新增 list/restore/permanent_delete |
| `server/apps/system_mgmt/nats/auth.py` / `nats/users.py` / `nats/common.py` | 活动组织投影 |
| `server/apps/core/utils/current_team_scope.py` | 拒绝归档 `current_team` |
| `server/apps/system_mgmt/utils/group_filter_mixin.py` | 活动组织范围 |
| `server/apps/system_mgmt/viewset/user_viewset.py` | 用户组织编辑只允许活动组织 |
| `server/apps/system_mgmt/services/user_sync_service.py` | 对账归档、`_sync_groups` 全局复用、根复用、删源顺序 |
| `server/apps/system_mgmt/viewset/user_sync_source_viewset.py` | destroy 先检查 running 再停调度 |
| `server/apps/system_mgmt/language/{zh-Hans,en}.yaml` | 归档相关文案 |
| `server/apps/system_mgmt/tests/test_group_archive_service.py` | **新建** 服务层与并发/授权反例 |
| `server/apps/system_mgmt/tests/test_group_viewset_api.py` | API 行为更新 |
| `server/apps/system_mgmt/tests/test_user_sync_service.py` / `test_user_sync_source_viewset.py` | 同步归档与删源 |
| `web/src/app/system-manager/api/group/index.ts` | 归档 API |
| `web/src/app/system-manager/types/...` | **新建** 归档独立类型 |
| `web/src/app/system-manager/components/.../ArchivedGroupDrawer.tsx` | **新建** Drawer |
| `web/src/app/system-manager/components/system-manager-group-tree/index.tsx` | 下拉入口 + 文案 |
| `web/src/app/system-manager/(pages)/user/structure/page.tsx` / `hooks/useUserStructure.ts` | 接线与刷新 |
| `web` i18n 文案文件（按现有 system-manager 惯例） | 中英文 |

---

### Task 1: Group.is_delete 模型与迁移

**Files:**
- Modify: `server/apps/system_mgmt/models/user.py`（`Group`）
- Create: `server/apps/system_mgmt/migrations/0047_group_is_delete.py`（若已有更新迁移则顺延编号）
- Test: `server/apps/system_mgmt/tests/test_group_archive_service.py`

**Interfaces:**
- Produces: `Group.is_delete: bool`（默认 `False`，`db_index=True`）

- [ ] **Step 1: 写失败测试（字段尚不存在）**

```python
# server/apps/system_mgmt/tests/test_group_archive_service.py
import pytest
from apps.system_mgmt.models import Group

pytestmark = pytest.mark.django_db

def test_group_has_is_delete_default_false():
    g = Group.objects.create(name="archive-model-probe", parent_id=0)
    assert hasattr(g, "is_delete")
    assert g.is_delete is False
```

- [ ] **Step 2: 运行确认失败**

```bash
cd server && uv run pytest apps/system_mgmt/tests/test_group_archive_service.py::test_group_has_is_delete_default_false -v --create-db
```

Expected: FAIL（`is_delete` 不存在或迁移未应用）

- [ ] **Step 3: 模型 + 迁移**

在 `Group` 增加：

```python
is_delete = models.BooleanField(default=False, db_index=True)
```

```bash
cd server && uv run python manage.py makemigrations system_mgmt --name group_is_delete
```

- [ ] **Step 4: 测试通过**

```bash
cd server && uv run pytest apps/system_mgmt/tests/test_group_archive_service.py::test_group_has_is_delete_default_false -v --create-db
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/apps/system_mgmt/models/user.py server/apps/system_mgmt/migrations/*group_is_delete*.py server/apps/system_mgmt/tests/test_group_archive_service.py
git commit -m "$(cat <<'EOF'
feat(system_mgmt): Group 增加 is_delete 以支持组织归档

EOF
)"
```

---

### Task 2: ArchiveService — 归档根判定、用户校验、手工归档

**Files:**
- Create: `server/apps/system_mgmt/services/group_archive_service.py`
- Modify: `server/apps/system_mgmt/viewset/group_viewset.py`（`delete_groups` 改为调用服务）
- Modify: `server/apps/system_mgmt/language/zh-Hans.yaml`、`en.yaml`
- Test: `server/apps/system_mgmt/tests/test_group_archive_service.py`、`test_group_viewset_api.py`

**Interfaces:**
- Produces:

```python
# group_archive_service.py
from dataclasses import dataclass

@dataclass(frozen=True)
class ArchiveReject:
    message_key: str
    affected_users: list[dict]  # [{"username","domain"}] 可选

class GroupArchiveService:
    @staticmethod
    def is_archive_root(group: Group, parent: Group | None) -> bool: ...

    @staticmethod
    def collect_subtree_ids(root_id: int) -> list[int]: ...

    @staticmethod
    def archive_subtree(*, actor, group_id: int) -> dict:
        """成功: {"result": True, "archived_ids": [...]}
        失败: {"result": False, "message": str, "affected_users": [...]?}
        事务内: 锁 Group→User；锁后重算剩余活动组织；保留 group_list；
        on_commit: clear 权限/菜单缓存 + log_operation
        """
```

归档根：`is_delete=True` 且（`parent_id==0` 或父不存在或父 `is_delete=False`）。

拒绝条件（与规格一致）：Default/虚拟顶、子树含 `sync_source`、非超管目标不在 `actor.group_list`、锁后用户无剩余活动组织。

- [ ] **Step 1: 写失败测试**

```python
def test_archive_keeps_group_list_and_sets_is_delete(db):
    parent = Group.objects.create(name="p-arch", parent_id=0)
    child = Group.objects.create(name="c-arch", parent_id=parent.id)
    other = Group.objects.create(name="other-arch", parent_id=0)
    user = User.objects.create(username="u1", domain="domain.com", group_list=[parent.id, other.id])
    # actor 超管 stub
    from apps.system_mgmt.services.group_archive_service import GroupArchiveService
    result = GroupArchiveService.archive_subtree(actor=_super_actor(), group_id=parent.id)
    assert result["result"] is True
    parent.refresh_from_db(); child.refresh_from_db(); user.refresh_from_db()
    assert parent.is_delete is True and child.is_delete is True
    assert parent.id in user.group_list and child.id in user.group_list  # 若用户本就只有 parent，需另测拒绝

def test_archive_rejects_when_user_would_have_no_active_group(db):
    g = Group.objects.create(name="only", parent_id=0)
    User.objects.create(username="lonely", domain="domain.com", group_list=[g.id])
    result = GroupArchiveService.archive_subtree(actor=_super_actor(), group_id=g.id)
    assert result["result"] is False
    assert g.is_delete is False

def test_archive_rejects_synced_subtree(db):
    # 创建带 sync_source 的组，期望拒绝
    ...
```

同时更新 `test_delete_groups_*`：物理删除断言改为 `is_delete=True`；「有用户则拒绝」改为「仅当无其他活动组织才拒绝」。

- [ ] **Step 2: 跑测确认失败**

```bash
cd server && uv run pytest apps/system_mgmt/tests/test_group_archive_service.py -k archive -v --create-db
```

- [ ] **Step 3: 实现 ArchiveService.archive_subtree + delete_groups 接线**

关键实现要点：

```python
with transaction.atomic():
    groups = list(Group.objects.select_for_update().filter(id__in=sorted(subtree_ids)))
    users = list(User.objects.select_for_update().filter(...overlap subtree...).order_by("id"))
    # 重新计算每位用户去掉 subtree 后是否还有 is_delete=False 的组织
    Group.objects.filter(id__in=subtree_ids).update(is_delete=True)
    transaction.on_commit(lambda: _clear_caches_and_log(...))
```

文案 key 示例：`error.group_archive_users_need_active_org`、`error.synced_groups_archive_forbidden`（可复用/改写 `synced_groups_delete_forbidden`）。

- [ ] **Step 4: 测试通过**

```bash
cd server && uv run pytest apps/system_mgmt/tests/test_group_archive_service.py apps/system_mgmt/tests/test_group_viewset_api.py -k "archive or delete_groups" -v
```

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(system_mgmt): 手工删除改为归档并集中到 ArchiveService

EOF
)"
```

---

### Task 3: 归档列表、恢复（递归子树）、永久删除 API

**Files:**
- Modify: `group_archive_service.py`、`group_viewset.py`、language yaml
- Test: `test_group_archive_service.py`、`test_group_viewset_api.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class ArchivedRootItem:
    id: int
    name: str
    parent_id: int
    kind: str  # local | synced_active_source | synced_deleted_source
    can_restore: bool
    can_permanently_delete: bool
    children: list[dict]  # 只读子树节点

@staticmethod
def list_archived_roots(*, actor) -> list[ArchivedRootItem]: ...

@staticmethod
def restore_archived_root(*, actor, group_id: int) -> dict:
    """递归将根及其完整归档子树 is_delete=False；on_commit 清缓存 + 恢复日志"""

@staticmethod
def permanently_delete_archived_root(*, actor, group_id: int) -> dict:
    """校验归档根+授权；锁后用户校验；从 group_list 移除子树；物理删除"""
```

kind 判定：
- 无 `sync_source_id` 且 external_id 非 `user-sync:` → `local`
- `sync_source_id` 仍在 → `synced_active_source`
- `sync_source_id` 空且 `external_id` 匹配 `user-sync:<id>:...` → `synced_deleted_source`

非超管：列表过滤根 id ∈ `actor.group_list`；restore/permanent_delete 再次校验。

- [ ] **Step 1: 失败测试**

```python
def test_restore_recursively_clears_is_delete_on_subtree(db): ...
def test_restore_rejects_non_root_archived_node(db): ...
def test_list_archived_roots_hides_unauthorized_for_nonsuperuser(db): ...
def test_permanent_delete_removes_group_list_refs(db): ...
def test_synced_kind_capabilities(db): ...
```

- [ ] **Step 2: 跑测失败 → 实现 actions**

```python
# group_viewset.py
@action(detail=False, methods=["GET"])
@HasPermission("user_group-Delete Group")  # 或 View+Delete 按现有习惯；规格要求 Delete
def list_archived_groups(self, request): ...

@action(detail=False, methods=["POST"])
@HasPermission("user_group-Delete Group")
def restore_archived_groups(self, request): ...  # body: {"id": ...}

@action(detail=False, methods=["POST"])
@HasPermission("user_group-Delete Group")
def permanently_delete_archived_groups(self, request): ...
```

- [ ] **Step 3: 测试通过并 Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(system_mgmt): 归档列表、递归恢复与永久删除接口

EOF
)"
```

---

### Task 4: 活动组织投影收敛

**Files:**
- Modify: `group_utils.py`、`nats/auth.py`、`nats/users.py`、`nats/common.py`（若角色继承读 Group）、`current_team_scope.py`、`group_filter_mixin.py`、`user_viewset.py`
- Test: 新建或扩展 `test_active_group_projection.py`、相关现有 NATS/current_team 测试

**Interfaces:**
- Produces: 所有「正常使用」查询默认 `filter(is_delete=False)`；归档 Drawer/ArchiveService 显式查含归档。

必改点（规格）：
- `build_user_authorization_context` 的 Group queryset
- `get_assignable_groups`、`search_groups`
- `GroupUtils.get_group_with_descendants*` 构建 children_map 时排除归档（或提供 `include_deleted=` 参数，默认 False）
- `resolve_current_team_data_scope`：若 current_team 对应组织 `is_delete=True` 或不存在 → `BaseAppException` 明确错误
- 用户编辑组织：目标必须活动

- [ ] **Step 1: 失败测试**

```python
def test_assignable_groups_excludes_archived(db): ...
def test_search_groups_excludes_archived(db): ...
def test_auth_context_excludes_archived_even_if_in_group_list(db): ...
def test_current_team_rejects_archived_group(db): ...
```

- [ ] **Step 2: 实现过滤 → 测试通过 → Commit**

```bash
git commit -m "$(cat <<'EOF'
fix(system_mgmt): 活动组织投影排除已归档组织

EOF
)"
```

---

### Task 5: 同步对账归档、子树/根复用、删源顺序

**Files:**
- Modify: `user_sync_service.py`（`_reconcile_synced_directory`、`_sync_groups`、`_get_or_create_root_group`、`delete_user_sync_source`）
- Modify: `user_sync_source_viewset.py`（`destroy`）
- Test: `test_user_sync_service.py`、`test_user_sync_source_viewset.py`

**Interfaces / 行为:**

1. `_reconcile_synced_directory`：stale 子树改为 `GroupArchiveService` 风格归档（或内部共享锁/更新），**保留** `group_list`，不再 `_clear_dangling_group_list_references` 对 stale 组织。
2. `_sync_groups`：按 `sync_source + scoped_external_id` **全局** `filter`（含归档），命中则 `is_delete=False`、更新 parent/name。
3. `_get_or_create_root_group`：
   - 优先 `Group.objects.filter(sync_source=source, external_id=scoped).first()`（含归档）→ 清 `is_delete`、保 ID；
   - 禁止仅因 `(parent_id=0, name)` 绑定无关本地根；冲突显式 `ValueError`/业务错误。
4. `destroy` / `delete_user_sync_source`：
   - 事务内 `select_for_update` source；
   - `UserSyncRun.status=RUNNING` → 拒绝，**不**调用 `delete_sync_periodic_task`；
   - 可删后再停周期任务 → 归档根树 → 删同步用户 → 删 source。

- [ ] **Step 1: 失败测试**

```python
def test_reconcile_archives_stale_groups_keeping_group_list(db): ...
def test_sync_groups_reuses_archived_by_scoped_external_id_across_parents(db): ...
def test_get_or_create_root_reactivates_archived_root_same_id(db): ...
def test_get_or_create_root_rejects_unrelated_local_name_collision(db): ...
def test_destroy_while_running_rejects_without_removing_periodic_task(db): ...
```

- [ ] **Step 2: 实现 → 测试通过 → Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(system_mgmt): 同步对账改归档并修复根复用与删源顺序

EOF
)"
```

---

### Task 6: 前端 ArchivedGroupDrawer 与入口

**Files:**
- Modify: `web/src/app/system-manager/api/group/index.ts`
- Create: 归档类型文件（勿污染正常 `Group` 树类型）
- Create: `ArchivedGroupDrawer` 组件
- Modify: `system-manager-group-tree/index.tsx`、`structure/page.tsx`、`useUserStructure.ts`
- i18n 中英文

**行为:**
- 「添加根组织」→ Dropdown：添加根组织 / 恢复归档组织
- 原删除文案→归档；成功后刷新树 + login 组织上下文；选中节点若已归档则 clear
- Drawer：只展示归档根+只读子树；按钮看 `can_restore` / `can_permanently_delete`
- 永久删除确认含资产自处理提示
- `current_team` 归档：不另做强制重选；依赖后端错误 + `message.error`

- [ ] **Step 1: API 与类型**

```typescript
// api/group/index.ts 增加
listArchivedGroups()
restoreArchivedGroup(params: { id: number })
permanentlyDeleteArchivedGroup(params: { id: number })
// deleteTeam 仍打 delete_groups，语义已是归档
```

- [ ] **Step 2: Drawer + 树入口接线**

- [ ] **Step 3: 前端类型检查 / 相关单测（若有）**

```bash
cd web && npx tsc --noEmit -p tsconfig.json  # 或项目惯用命令；勿改 tsconfig.json
```

- [ ] **Step 4: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(web): 组织归档 Drawer 与恢复入口

EOF
)"
```

---

### Task 7: 聚焦回归与规格反例矩阵

**Files:** 仅测试与必要修缮

必跑（PostgreSQL，`--create-db` 若库脏）：

```bash
cd server && uv run pytest \
  apps/system_mgmt/tests/test_group_archive_service.py \
  apps/system_mgmt/tests/test_group_viewset_api.py \
  apps/system_mgmt/tests/test_user_sync_service.py \
  apps/system_mgmt/tests/test_user_sync_source_viewset.py \
  -v --create-db
```

反例清单（规格）：
- [ ] 非超管越权列表/恢复/永久删除
- [ ] 归档 `current_team` 被拒
- [ ] 同步 running 删源拒绝且周期任务仍在
- [ ] 同步根归档后再同步：同 ID 恢复
- [ ] 永久删除与用户组织并发（锁后重算）
- [ ] `git diff --check`；确认未改无关文件

- [ ] **Step 最终 Commit（若有修缮）**

```bash
git commit -m "$(cat <<'EOF'
test(system_mgmt): 补齐组织归档授权与同步反例

EOF
)"
```

---

## Spec Coverage Checklist

| 规格要求 | Task |
|---|---|
| `is_delete` 模型 | 1 |
| 手工归档、保留 group_list、用户活动组织校验 | 2 |
| 归档根定义、列表 capability、递归恢复、永久删除 | 3 |
| 非超管授权二次校验 | 3 |
| 活动组织投影 / NATS / current_team | 4 |
| 对账归档、子树 external_id 复用 | 5 |
| 同步根复用与冲突 | 5 |
| 删源先查 running 再停调度 | 5 |
| 事务锁顺序 + on_commit | 2/3/5 |
| 前端 Drawer / 下拉 / 文案 | 6 |
| 反例测试矩阵 | 7 |
| 不改 LoginModule 旧路径 | 全局约束 |

## Self-Review Notes

- 无 TBD 占位；迁移编号实施时按仓库最新顺延。
- `ArchivedRootItem.kind` 三值与规格一致。
- 恢复语义已写明递归整棵归档子树。
