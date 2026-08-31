# 组织归档设计

## 目标

在系统管理中支持组织软删除（归档）、恢复与永久删除。正常树、选择器、`current_team`、权限范围与 NATS 授权上下文只暴露活动组织；不检查、统计、迁移或阻断各业务模块资产。

## 非目标

- 不改认证源 / 登录模块（LoginModule）旧同步路径（`tasks._sync_groups`）；该路径视为弃用旁路，另开任务。
- 不调整 `(name, parent_id)` 唯一约束；归档组织继续占用名称。
- 不改变组织 ID、名称、父子关系、角色或 `external_id`（归档本身不改这些字段）。
- 不扩展同步用户「无有效归属即删除」的判定语义；对齐现有 `_sync_users` / reconcile。

## 架构选型

采用 **`ArchiveService` + 活动组织查询入口**（方案 1）：

- 归档 / 恢复 / 永久删除 / 列表 capability 字段集中在服务层。
- 树、NATS、`current_team`、用户校验等统一走活动组织查询（`is_delete=False`）。
- 归档 Drawer 使用独立查询，不复用正常树接口。

不采用默认 Manager 排除归档（易踩错），也不采用各调用点分散手写过滤（易漏）。

## 模型

`Group` 仅新增：

```python
is_delete = models.BooleanField(default=False, db_index=True)
```

归档不修改用户 `group_list`（关联 ID 保留，便于恢复）；活动投影不得因此把归档组织展示出来。

## 归档根（接口契约）

**归档根**定义为同时满足：

1. `is_delete=True`
2. 满足以下之一：
   - `parent_id=0`，或
   - 父组织不存在，或
   - 父组织为活动状态（`is_delete=False`）

父组织亦为归档时，该节点**不是**归档根，仅作为某归档根子树中的只读后代。

归档列表只返回归档根；每个根可附带只读子树供 Drawer 展示。恢复与永久删除**仅允许以归档根为操作目标**；对非根归档节点的写请求必须拒绝。

### 非超管授权边界

延续现有手工删除对普通用户按 `request.user.group_list` 校验目标节点的边界（`GroupViewSet.delete_groups`）。归档后 `group_list` 仍保留组织 ID，因此：

- **归档列表**：只返回操作者有权限操作的归档根（根 ID 落在其授权组织范围内；超管不受此限）。
- **恢复 / 永久删除**：服务端必须再次校验该归档根在操作者授权组织范围内。
- **不得**仅依赖前端隐藏按钮；越权请求一律拒绝。

权限点仍为 `user_group-Delete Group`（归档 / 恢复 / 永久删除共用）。

## 手工归档

入口：现有 `GroupViewSet.delete_groups` **直接改为归档**（不再物理删除）。权限仍为 `user_group-Delete Group`。

行为：

1. 收集目标及完整子树。
2. 保护：`Default` 根组织、虚拟顶组织 → 拒绝。
3. 子树任一组织关联 `sync_source` → 拒绝。
4. 非超管：目标组织须在 `request.user.group_list` 授权范围内（与现删除一致）。
5. 在事务内锁定目标子树与关联用户后，对每位关联用户重新计算：移除目标子树后若不存在其他**活动**组织 → 拒绝，并返回受影响用户。
6. 通过后整棵子树 `is_delete=True`，**保留** `group_list`。
7. `transaction.on_commit` 后清权限/菜单缓存（子树 overlapping 成员 ∪ 当前操作者），写归档操作日志。

## 恢复与永久删除

新增归档列表、恢复、永久删除接口。权限与归档相同：`user_group-Delete Group`。

### 列表 capability（服务端权威）

服务端返回 `kind`、`can_restore`、`can_permanently_delete`；前端不得根据 `sync_source` 自行推断。列表结果已按上一节授权边界过滤。

建议 `kind` 取值：

- `local`：本地手工归档 → `can_restore=true`，`can_permanently_delete=true`
- `synced_active_source`：同步源仍存在 → `can_restore=false`，`can_permanently_delete=true`（不静默改名；管理员永久删除以释放名称。仍归档时同一 `external_id` 再出现仍复用原 ID；永久删除后再出现则走新建）
- `synced_deleted_source`：同步源已删且 `external_id` 符合 `user-sync:<source>:...` → `can_restore=false`，`can_permanently_delete=true`

| 情形 | kind | 手工恢复 | 永久删除 |
|---|---|---|---|
| 本地归档 | `local` | 可 | 可 |
| 同步源仍存在（对账自动归档） | `synced_active_source` | 否 | 可 |
| 同步源已删除且 external_id 匹配 | `synced_deleted_source` | 否 | 可 |

操作粒度：仅对**归档根**恢复 / 永久删除；子节点只读展示。写接口须再次校验授权范围与「目标必须是归档根」。

### 恢复

对归档根发起恢复时，须**递归**将该根及其完整归档子树全部恢复为活动状态（整棵子树 `is_delete=False`），不得只恢复根节点而留下仍归档的后代。恢复成功后：`transaction.on_commit` 清理 overlapping 成员与当前操作者的权限/菜单缓存，并写恢复操作日志。

### 永久删除

1. 校验目标为归档根，且操作者有权。
2. 在事务内锁定子树与关联用户后，按活动组织规则重新计算用户归属（去掉子树后须仍有活动组织）。
3. 通过后从用户 `group_list` 移除子树 ID，再物理删除子树。
4. `transaction.on_commit` 后清缓存（overlapping 成员 ∪ 当前操作者）。
5. 确认文案提示管理员先自行处理业务资产。同步对账归档额外说明：删除后原 ID 不保留，外部目录再次出现该组织时同步走新建。
6. 不静默给归档组织改占用名。同父级名称仍被归档占用时，同步继续 `group_name_conflict`，由管理员永久删除后再同步。

## 活动组织投影

凡面向正常使用的组织数据，只暴露 `is_delete=False`。`group_list` 中残留的归档 ID 不进入这些投影。

必须收敛的入口（不可只改 `search_group_list`）：

- `GroupUtils` 子树查询
- NATS 认证上下文 `build_user_authorization_context`（含 `group_list` / `group_tree`，影响右上角组织切换）
- NATS 可分配组织 `get_assignable_groups`
- NATS 公共组织搜索 `search_groups`
- NATS `get_group_id`、`get_user_group_tree.group_list`（活动投影不得含归档 ID）
- NATS `search_channel_list` / `search_opspilot_nats_channels` 在 `include_children=True` 时只扩活动子孙
- 经 `GroupUtils` / `current_team` 的 scoped 授权（如 `_get_actor_user_scope`）
- 用户组织编辑校验
- 角色继承沿父链查找
- 角色分配/回收与角色下组织列表（归档组织不可再绑/解绑，列表不展示）
- `current_team` / `GroupFilterMixin` 数据范围
- 系统管理正常组织树与各类组织选择器

行为约定：

- 超管也不能把归档组织当作 `current_team`。
- 请求携带已归档 `current_team` → 后端拒绝并返回明确错误；前端用现有 `message.error` 展示，不做额外强制重选流程。
- 归档 Drawer 独立 HTTP 查询；其他业务模块通过独立 NATS `get_archived_groups` 分页拉取**全部**已归档组织（含非根后代，不含 capability），自行处理其资产或数据，系统管理不代为迁移或删除业务数据。
- 相对旧物理删除：旧接口不检查 `current_team`，且成功删除后超管路径可能对幽灵 ID 扩范围；归档实现须收紧为「归档组织一律拒绝作为 `current_team`」。

### NATS 说明（实现必改点）

- **认证上下文**：超管当前 `Group.objects.all()`、普通用户从 `group_list` 扩树；必须过滤 `is_delete=False`，否则归档组织会出现在右上角组织树。
- **可分配组织**：超管/普通用户返回值不得含归档组织，避免把资源分配到已归档组织。
- **公共搜索**：`search_groups` 不得返回归档组织。
- **按名查根**：`get_group_id` 只返回活动根；归档根走 `get_archived_groups`。
- **用户组织树**：`get_user_group_tree` 的 `group_list` / `group_tree` 只含活动组织。
- **通道按组织扩子树**：`search_channel_list` / `search_opspilot_nats_channels` 的 `include_children=True` 只扩活动子孙；显式传入的归档组织 ID 且 `include_children=False` 仍可按该 ID 对账通道。
- **模块查询归档**：`get_archived_groups(page, page_size)` 返回 `{items:[{id,name,parent_id}], count, page, page_size}`；有分页上界；不按操作者授权过滤（供内部模块对账资产）。管理端归档列表仍走独立 HTTP API。

## 同步（仅 UserSyncSource）

### 对账

`_reconcile_synced_directory`：stale 组织由物理删除改为归档完整子树；保留用户 `group_list`；不再在对账中清除用户对 stale 组织的引用。对账写路径须走与 `ArchiveService` 一致的事务/锁策略（见下文）。

### 组同步复用（非根）

`_sync_groups` 按 `sync_source + scoped external_id` **全局**定位（含已归档），命中则复用原 ID 并恢复活动（清 `is_delete`）、必要时更新父/名，保证组织移动后 ID 稳定。

### 同步根复用（`_get_or_create_root_group`）

同步根**不经过** `_sync_groups`，当前以 `(parent_id=0, name=root_group_name)` 查找。必须改为与子树同等的「复用原记录」语义：

1. **优先**按 `sync_source + scoped external_id` 全局定位已有根（含 `is_delete=True`）。
2. 同步源仍存在、根已被归档后再次同步：将该根 `is_delete=False`，**保留原 ID**，再按需更新名称等字段。
3. **禁止**仅因同名而悄然绑定无关本地组织（例如本地手工根与同步根撞名）。
4. 根名称变更，或与无关本地同名组织冲突时：返回**明确冲突错误**，不得覆盖错误记录的 `sync_source` / `external_id`，不得新建第二条「假根」顶替已归档原根而不说明原因。

### 同步用户删除

「无有效外部组织归属」时按现有同步用户删除语义删除；对齐现状，不扩展空部门/无效部门/根部门判定。

### 删除同步源（拒绝顺序）

现状 `UserSyncSourceViewSet.destroy` 会先 `delete_sync_periodic_task()` 再进删除逻辑；若随后因「同步运行中」拒绝，会造成**源仍在但周期任务已停**。必须改为：

1. 在同一事务内锁定 `UserSyncSource`（`select_for_update`）。
2. 检查是否存在 `UserSyncRun.status=running`。
3. **若有**：直接拒绝，**不修改**周期任务，不归档、不删用户、不删 source。
4. **仅确认可删后**：停止周期任务 → 归档根及子树 → 删除同步用户 → 删除 source。
5. `SET_NULL` 后保留 `external_id`，供归档列表分类为 `synced_deleted_source`。

前端：同步任务进行中禁用删除按钮（体验层）；后端上述顺序为权威（防绕过与竞态）。

删源后的归档树：不可手工恢复，可永久删除。

## 事务与锁策略（ArchiveService）

手工归档、恢复、永久删除、同步对账归档、删除同步源都可能并发触及同一组织/用户。现有 `delete_groups` 为无锁全量树读取后直接删除，归档引入「剩余活动组织」校验后存在 TOCTOU。`ArchiveService`（及删源编排）须在事务内：

1. **锁定目标根与子树**（`select_for_update`，组织按 id 排序加锁）。
2. **锁定关联用户**（按 id 排序加锁），并在持锁后**重新计算**「移除子树后是否仍有活动组织」。
3. 更新组织状态 / 用户 `group_list` / 物理删除等写操作。
4. **`transaction.on_commit`** 后再清理权限与菜单缓存、写操作日志等外部副作用。

涉及同步源时，锁顺序固定为：

`UserSyncSource`（若有）→ `Group`（按 id）→ `User`（按 id）

避免删源、手工归档、对账交叉死锁。校验失败必须整事务回滚，不留下半更新状态。

## 前端

- 组织树顶部「添加根组织」改为下拉：添加根组织 / 恢复归档组织。
- 原删除入口文案与行为改为归档（调用已改为归档的 `delete_groups`）。
- 新建 `ArchivedGroupDrawer`：归档根 + 只读子树；操作由后端 capability 控制。
- `synced_active_source` 归档根：不可手工恢复，展示永久删除；确认文案说明删除后若外部再出现则新建。子节点操作列留空。不展示 `--` 作为无操作占位。
- 归档 / 恢复 / 永久删除成功后刷新正常树与登录组织上下文；若当前选中树节点被归档则清除选中。后端须使操作者 `token_info` 失效，以便随后的 `login_info` 重建活动组织树；其他已登录全量树用户不在本档范围内。
- 永久删除确认必须含资产处理提示。
- 独立归档类型与中英文文案，避免归档字段进入正常树 / 用户选择类型。

## 关键代码入口

- 手工组织操作：`server/apps/system_mgmt/viewset/group_viewset.py::GroupViewSet.delete_groups`
- 组织树工具：`server/apps/system_mgmt/utils/group_utils.py::GroupUtils`
- 用户组织校验：`server/apps/system_mgmt/viewset/user_viewset.py`
- 授权与公开组织 RPC：`server/apps/system_mgmt/nats/auth.py`、`nats/users.py`（含 `get_archived_groups`）、`nats/channels.py`
- 归档写路径：`server/apps/system_mgmt/services/group_archive_service.py`
- 归档查询：`server/apps/system_mgmt/services/archived_group_query.py`
- RPC 客户端：`server/apps/rpc/system_mgmt.py`
- `current_team`：`server/apps/core/utils/current_team_scope.py`、`group_filter_mixin.py`
- 同步：`user_sync_service.py`（含 `_get_or_create_root_group`、`_sync_groups`、`_reconcile_synced_directory`）、`user_sync_source_viewset.py::destroy`
- 前端：`structure/page.tsx`、`useUserStructure.ts`、`system-manager-group-tree`、`api/group`

## 测试与交付

- 隔离 worktree + 分支 `codex/organization-archive`；不覆盖当前工作区无关改动（`enterprise`、`web/next-env.d.ts`、`web/tsconfig.json`）。
- 使用开发 `.env` 的 PostgreSQL；逻辑库 `bklite_org_archive` 时 pytest 库为 `test_bklite_org_archive`。
- 需要干净库时用 `--create-db`，不盲目复用失败库。
- 聚焦验证：模型/迁移、手工归档与用户校验、活动投影、同步对账与删源、前端 Drawer/文案、`git diff --check` 与范围。

### 必测反例 / 并发矩阵

- 非超管越权：列表不得出现无权归档根；恢复/永久删除越权目标必须拒绝。
- 归档后仍以该组织为 `current_team` 的请求被拒绝。
- 同步运行中删源：拒绝，且周期任务仍保持删除前状态（未被拆掉）。
- 同步根归档后再同步：原 ID 恢复活动（`is_delete=False`）；同名无关本地组织冲突时显式失败。
- 永久删除与用户组织并发编辑：持锁后重算，不出现「无活动组织用户」脏数据。
- 手工归档与对账/删源并发触及同一子树：事务回滚或串行后状态一致。

### 推荐实现顺序

1. 创建隔离工作区与干净分支
2. 写并运行模型/手工归档的失败测试（含授权与锁后重算）
3. 实现 `is_delete`、迁移、归档与用户校验
4. 收敛活动组织查询
5. 改同步对账、子树/根复用恢复及同步源删除顺序
6. 前端 Drawer、API 类型与文案
7. 聚焦回归（含并发与授权反例）

## 已确认决策摘要

- 归档保留 `group_list`；活动 UI/RPC 不展示归档组织。
- `delete_groups` 改为归档；永久删除仅在归档 Drawer。
- 只做 UserSyncSource；认证源旧路径不改。
- 同步进行中：前端禁用删源 + 后端拒绝；**先检查 running，再停调度**。
- `Default`/虚拟顶禁止归档。
- 归档 `current_team`：后端拒绝 + 前端 `message.error`。
- 恢复/永久删除权限复用 `user_group-Delete Group`；列表与写操作均按授权范围过滤/校验。
- Drawer 仅对归档根可操作；归档根定义见上文接口契约。恢复归档根时递归恢复其完整归档子树为活动状态，并 on_commit 清缓存、写恢复日志。
- 同步根与子树均须按 `sync_source + scoped external_id` 复用原 ID；根路径不得悄然绑错本地组织。
- 对账归档占用名称直至永久删除；不静默改占用名。同步源仍在的归档根可永久删除、不可手工恢复。永久删除后外部再出现走新建。
- `ArchiveService` 事务内加锁并在锁后重算用户活动组织；缓存等副作用放 `on_commit`。
- 其他业务模块通过 NATS `get_archived_groups` 自行查询已归档组织并处理资产；系统管理不代为检查或迁移业务数据。
