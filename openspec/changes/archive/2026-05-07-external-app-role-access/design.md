## Context

系统通过 `App` 表管理所有应用（内置 + 外部），通过 `Role` 表管理各应用的角色（`Role.app` 字段关联应用名）。`get_client(username)` 通过"用户拥有哪些 Role.app → 过滤 App 列表"来决定用户可见哪些应用。

当前存在两个断点：
1. 外部应用创建时只写 `App` 表，不创建对应 `Role`，用户永远无法被授权
2. `get_role_tree` API 硬过滤 `is_build_in=True`，即使手动创建了 Role，管理 UI 中也不可见

## Goals / Non-Goals

**Goals:**
- 外部应用创建时自动创建 `user` 角色，保证可授权
- 外部应用删除时级联删除对应角色，避免孤立数据
- 角色分配 UI（编辑组织/用户）中能看到外部应用的 `user` 角色
- 授权后，普通用户在 ops-console 和应用切换列表中可见外部应用

**Non-Goals:**
- 不为外部应用创建 `admin`/`normal` 等多个角色（外部应用语义简单，仅需"有无访问权"）
- 不处理历史已存在的外部应用数据修复（留给管理员手动或运维脚本处理）
- 不改动前端代码（现有权限过滤和角色树展示逻辑已具备）

## Decisions

### D1: 在 Serializer 层而非 ViewSet 层创建角色

**选择**：在 `AppSerializer.create()` 中创建 Role，并用 `transaction.atomic` 包裹。

**理由**：Serializer 的 `create()` 是数据写入的天然收口，Django REST Framework 在这里已有事务语义保障。若放在 ViewSet，需要覆盖更多方法（list/create/update），侵入面更大。

**替代方案**：Django `post_save` signal → 拒绝，signal 难以追踪、不易测试，且无法保证与主事务同步。

### D2: 去除 `get_role_tree` 的 `is_build_in` 过滤而非新增参数

**选择**：直接移除过滤条件，让所有有 Role 记录的应用都出现在角色树中。

**理由**：外部应用只要有 Role 就应该可被授权，`is_build_in` 在这个查询中没有业务价值。新增参数会增加接口复杂度，而现有调用方（前端 `getRoleList`）已经传入完整 `client_list`，不需要区分。

**替代方案**：新增 `include_external` 参数 → 不必要的复杂性。

### D3: 角色名固定为 `user`

**选择**：外部应用只创建一个名为 `user` 的角色。

**理由**：`get_client` 通过 `Role.app` 判断可见性，只要存在任意角色即可。外部应用是第三方系统，bk-lite 无法管理其内部权限分级，`user` 表示"有权访问"语义清晰。

## Risks / Trade-offs

- **[风险] 历史外部应用无 Role 记录** → 现有数据不受影响，普通用户依然不可见；管理员可通过 django shell 或 management command 补录，不影响本次功能交付
- **[风险] `get_role_tree` 去除过滤后，外部应用 Role 显示在分配 UI 中，但内置应用的 admin/normal 等多角色已有成熟处理** → 外部应用只有一个 `user` 角色，树形结构简洁，不影响现有 UI 渲染逻辑
- **[风险] 删除外部应用时，已分配给用户/组的 Role ID 成为悬空引用** → 级联删除 Role 后，`user.role_list` / `group.roles` 中的 ID 会变为无效；这与内置应用的删除行为一致（内置应用不允许删除），属于可接受的边界情况，后续可通过 clean job 处理

## Migration Plan

1. 部署新代码即生效，无 migration 文件
2. 回滚：回退代码即可；历史数据无破坏性变更
3. 历史外部应用修复（可选，非强制）：
   ```python
   from apps.system_mgmt.models import App, Role
   for app in App.objects.filter(is_build_in=False):
       Role.objects.get_or_create(name='user', app=app.name)
   ```

## Open Questions

- 无
