## Why

当前用户管理页已经具备禁用、锁定、密码有效期相关的底层数据基础，但列表接口和页面交互还没有把这些状态收敛成统一的管理能力。随着用户管理需求细化，系统需要在不新增数据库状态字段的前提下，为用户列表提供一致的状态展示、状态驱动操作和批量状态处理能力。

## What Changes

- 为用户列表引入派生 `status` 能力，按统一优先级对 `disabled`、锁定窗口和密码到期进行状态归并。
- 为用户管理后端新增统一 `change_status` 接口，支持 `enable`、`disable`、`unlock` 三类单条与批量状态动作。
- 为用户管理前端接入状态列、按状态变化的行内操作，以及“批量操作”下拉菜单。
- 保持现有数据库模型不变，不新增持久化 `status` 字段。
- 密码到期状态沿用系统现有的判定规则，不要求在本次变更中额外扩展到其他既有流程的结构调整。
- 保持现有 `search_user_list` 可见范围语义不变，不处理禁用后在线会话失效逻辑。

## Capabilities

### New Capabilities
- `user-status-management`: Covers derived user status calculation, unified user status change actions, and user management UI behaviors driven by status.

### Modified Capabilities

## Impact

- Affected backend code: `server/apps/system_mgmt/serializers/user_serializer.py`, `server/apps/system_mgmt/viewset/user_viewset.py`
- Affected frontend code: `web/src/app/system-manager/types/user.ts`, `web/src/app/system-manager/api/user/index.ts`, `web/src/app/system-manager/hooks/useUserStructure.ts`, `web/src/app/system-manager/components/user/tableColumns.tsx`, `web/src/app/system-manager/(pages)/user/structure/page.tsx`
- Affected APIs: `/system_mgmt/user/search_user_list/`, `/system_mgmt/user/get_user_detail/`, new `/system_mgmt/user/change_status/`
- Existing unrelated flows remain structurally unchanged in this change.
- No new dependencies and no database schema changes
