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

## 手工归档

入口：现有 `GroupViewSet.delete_groups` **直接改为归档**（不再物理删除）。权限仍为 `user_group-Delete Group`。

行为：

1. 收集目标及完整子树。
2. 保护：`Default` 根组织、虚拟顶组织 → 拒绝。
3. 子树任一组织关联 `sync_source` → 拒绝。
4. 对每位关联用户：移除目标子树后若不存在其他**活动**组织 → 拒绝，并返回受影响用户。
5. 通过后整棵子树 `is_delete=True`，**保留** `group_list`。
6. 清权限缓存与菜单缓存，写归档操作日志。

## 恢复与永久删除

新增归档列表、恢复、永久删除接口。权限与归档相同：`user_group-Delete Group`。

### 列表 capability（服务端权威）

服务端返回 `kind`、`can_restore`、`can_permanently_delete`；前端不得根据 `sync_source` 自行推断。

建议 `kind` 取值：

- `local`：本地手工归档 → `can_restore=true`，`can_permanently_delete=true`
- `synced_active_source`：同步源仍存在 → 均为 `false`（等同步按 external_id 带回）
- `synced_deleted_source`：同步源已删且 `external_id` 符合 `user-sync:<source>:...` → `can_restore=false`，`can_permanently_delete=true`

| 情形 | kind | 手工恢复 | 永久删除 |
|---|---|---|---|
| 本地归档 | `local` | 可 | 可 |
| 同步源仍存在（对账自动归档） | `synced_active_source` | 否 | 否 |
| 同步源已删除且 external_id 匹配 | `synced_deleted_source` | 否 | 可 |

操作粒度：仅对**归档根**恢复 / 永久删除；子节点只读展示。

### 永久删除

1. 按活动组织规则校验用户（去掉子树后须仍有活动组织）。
2. 通过后从用户 `group_list` 移除子树 ID。
3. 物理删除子树并清缓存。
4. 确认文案提示管理员先自行处理业务资产。

## 活动组织投影

凡面向正常使用的组织数据，只暴露 `is_delete=False`。`group_list` 中残留的归档 ID 不进入这些投影。

必须收敛的入口（不可只改 `search_group_list`）：

- `GroupUtils` 子树查询
- NATS 认证上下文 `build_user_authorization_context`（含 `group_list` / `group_tree`，影响右上角组织切换）
- NATS 可分配组织 `get_assignable_groups`
- NATS 公共组织搜索 `search_groups`
- 经 `GroupUtils` / `current_team` 的 scoped 授权（如 `_get_actor_user_scope`）
- 用户组织编辑校验
- 角色继承沿父链查找
- `current_team` / `GroupFilterMixin` 数据范围
- 系统管理正常组织树与各类组织选择器

行为约定：

- 超管也不能把归档组织当作 `current_team`。
- 请求携带已归档 `current_team` → 后端拒绝并返回明确错误；前端用现有 `message.error` 展示，不做额外强制重选流程。
- 归档 Drawer 独立查询。
- 相对旧物理删除：旧接口不检查 `current_team`，且成功删除后超管路径可能对幽灵 ID 扩范围；归档实现须收紧为「归档组织一律拒绝作为 `current_team`」。

### NATS 说明（实现必改点）

- **认证上下文**：超管当前 `Group.objects.all()`、普通用户从 `group_list` 扩树；必须过滤 `is_delete=False`，否则归档组织会出现在右上角组织树。
- **可分配组织**：超管/普通用户返回值不得含归档组织，避免把资源分配到已归档组织。
- **公共搜索**：`search_groups` 不得返回归档组织；归档列表走独立 HTTP API。

## 同步（仅 UserSyncSource）

### 对账

`_reconcile_synced_directory`：stale 组织由物理删除改为归档完整子树；保留用户 `group_list`；不再在对账中清除用户对 stale 组织的引用。

### 组同步复用

`_sync_groups` 按 `sync_source + scoped external_id` **全局**定位（含已归档），命中则复用原 ID 并恢复活动（清 `is_delete`）、必要时更新父/名，保证组织移动后 ID 稳定。

### 同步用户删除

「无有效外部组织归属」时按现有同步用户删除语义删除；对齐现状，不扩展空部门/无效部门/根部门判定。

### 删除同步源

- 前端：同步任务进行中禁用删除按钮。
- 后端：同步进行中删除接口必须拒绝（防绕过与竞态）。
- 顺序：归档根及子树 → 删除同步用户 → 删除 source；`SET_NULL` 后保留 `external_id` 供归档列表分类。
- 删源后的归档树：不可手工恢复，可永久删除。

## 前端

- 组织树顶部「添加根组织」改为下拉：添加根组织 / 恢复归档组织。
- 原删除入口文案与行为改为归档（调用已改为归档的 `delete_groups`）。
- 新建 `ArchivedGroupDrawer`：归档根 + 只读子树；操作由后端 capability 控制。
- 归档 / 恢复 / 永久删除成功后刷新正常树与登录组织上下文；若当前选中树节点被归档则清除选中。
- 永久删除确认必须含资产处理提示。
- 独立归档类型与中英文文案，避免归档字段进入正常树 / 用户选择类型。

## 关键代码入口

- 手工组织操作：`server/apps/system_mgmt/viewset/group_viewset.py::GroupViewSet.delete_groups`
- 组织树工具：`server/apps/system_mgmt/utils/group_utils.py::GroupUtils`
- 用户组织校验：`server/apps/system_mgmt/viewset/user_viewset.py`
- 授权与公开组织 RPC：`server/apps/system_mgmt/nats/auth.py`、`nats/users.py`
- `current_team`：`server/apps/core/utils/current_team_scope.py`、`group_filter_mixin.py`
- 同步：`user_sync_service.py`、`user_sync_source_viewset.py`
- 前端：`structure/page.tsx`、`useUserStructure.ts`、`system-manager-group-tree`、`api/group`

## 测试与交付

- 隔离 worktree + 分支 `codex/organization-archive`；不覆盖当前工作区无关改动（`enterprise`、`web/next-env.d.ts`、`web/tsconfig.json`）。
- 使用开发 `.env` 的 PostgreSQL；逻辑库 `bklite_org_archive` 时 pytest 库为 `test_bklite_org_archive`。
- 需要干净库时用 `--create-db`，不盲目复用失败库。
- 聚焦验证：模型/迁移、手工归档与用户校验、活动投影、同步对账与删源、前端 Drawer/文案、`git diff --check` 与范围。

### 推荐实现顺序

1. 创建隔离工作区与干净分支
2. 写并运行模型/手工归档的失败测试
3. 实现 `is_delete`、迁移、归档与用户校验
4. 收敛活动组织查询
5. 改同步对账、复用恢复及同步源删除
6. 前端 Drawer、API 类型与文案
7. 聚焦回归

## 已确认决策摘要

- 归档保留 `group_list`；活动 UI/RPC 不展示归档组织。
- `delete_groups` 改为归档；永久删除仅在归档 Drawer。
- 只做 UserSyncSource；认证源旧路径不改。
- 同步进行中：前端禁用删源 + 后端拒绝。
- `Default`/虚拟顶禁止归档。
- 归档 `current_team`：后端拒绝 + 前端 `message.error`。
- 恢复/永久删除权限复用 `user_group-Delete Group`。
- Drawer 仅对归档根可操作。
