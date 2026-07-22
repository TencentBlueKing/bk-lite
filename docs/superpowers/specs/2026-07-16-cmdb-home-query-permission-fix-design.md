# CMDB 首页查询权限修复设计

- 日期：2026-07-16
- 状态：已批准，待实施计划
- 范围：`server/apps/cmdb`、`web/src/app/cmdb`
- 关联问题：projectmem #0307

## 1. 背景与根因

normal 角色具备 `search-View` 和 `asset_info-View`，但进入 CMDB 首页时，`CommonProvider` 会无条件请求 `GET /cmdb/api/model/`。`ModelViewSet.list` 自提交 `d2a39f706c` 起只接受 `model_management-View`，因此只读查询用户在进入首页时收到 403。

该提交修改前允许模型管理、资产和视图查询权限读取模型列表，但旧权限名 `asset_list-View`、`view_list-View` 已分别演进为 `asset_info-View`、`search-View`。直接恢复旧字符串仍会因 `HasPermission` 精确匹配而拒绝当前 normal 角色。

模型列表成功后，首页还会继续请求分类、模型实例统计和最近资产变更。若只修模型列表，分类和最近变更仍可能分别因 `model_management-View`、`operation_log-View` 返回 403，因此本设计按“首页完整只读链路无 403”验收，而不是只消除第一条报错。

## 2. 已确认产品口径

- CMDB 首页是查询入口，不是模型管理或操作日志管理入口。
- 具备 `search-View` 或 `asset_info-View` 的 normal 用户可以查看首页只读数据。
- 首页查询权限不得授予模型新增、编辑、删除能力，也不得授予完整操作日志页面访问能力。
- 模型、实例统计和最近变更仍须遵守现有组织、模型和实例数据范围。

## 3. 方案比较

### 3.1 原样恢复旧权限字符串

恢复 `model_management-View,asset_list-View,view_list-View`。改动最小，但两个旧权限名已不存在，无法修复当前角色，拒绝采用。

### 3.2 按当前权限名等价回滚，并收敛首页只读链路（采用）

模型和分类列表允许 `model_management-View`、`asset_info-View`、`search-View` 任一权限；实例统计允许资产或搜索查看权限。最近资产变更使用首页专用只读入口，避免放宽通用操作日志列表。该方案保持现有接口和过滤逻辑，权限语义准确，改动范围可控。

### 3.3 新建统一 CMDB 元数据 API

由单个首页 API 聚合模型、分类、统计和最近变更。长期边界更清楚，但引入新的聚合服务、响应合同和迁移范围，超出本次缺陷修复需要，不采用。

## 4. 设计

### 4.1 模型与分类元数据

- `ModelViewSet.list` 的功能权限改为 `model_management-View,asset_info-View,search-View`。
- `ClassificationViewSet.list` 使用相同准入权限。
- 只调整 GET 列表方法；create、update、destroy 和模型关系写操作继续使用原管理权限。
- 模型列表继续调用 `format_user_groups_permissions` 和 `ModelManage.search_model`，不跳过对象级及组织级过滤。

### 4.2 模型实例统计

- `InstanceViewSet.model_inst_count` 允许 `asset_info-View,search-View`。
- 继续使用 `format_user_groups_permissions` 生成实例权限范围，不向查询用户返回越权模型的统计。

### 4.3 最近资产变更

- 不放宽 `ChangeRecordViewSet.list`；完整操作日志列表继续要求 `operation_log-View`。
- 新增首页专用只读 action，允许 `asset_info-View,search-View`。
- 服务端固定限制为首页资产变更场景，沿用分页，限制单页最大数量；允许首页已有的“全部、我相关、高风险”过滤条件。
- 前端首页改用专用 action。用户即使自行去掉前端过滤参数，也不能通过该入口查询模型管理、配置管理等非首页场景记录。

### 4.4 错误处理

- 有首页查询权限的用户不应收到上述初始化请求的 403，也不应触发全局 `message.error`。
- 无 `search-View`、`asset_info-View`、相应管理权限的用户继续 fail-closed 返回 403。
- 单个首页卡片的非权限异常继续局部降级为空数据，不阻断搜索框和其他卡片。

## 5. 数据流

```text
normal(search-View 或 asset_info-View)
  -> CommonProvider
     -> 模型列表（当前查询权限 + 对象范围过滤）
  -> 首页 landing data
     -> 分类列表（当前查询权限）
     -> 模型实例统计（当前查询权限 + 实例范围过滤）
     -> 首页资产变更 action（固定场景 + 分页上限）
  -> 首页完整渲染，无权限错误提示
```

模型和操作日志的写入接口不在该数据流中，权限保持不变。

## 6. TDD 与验收

实现前先增加失败测试，确认旧代码稳定复现以下行为：

1. 仅 `search-View` 的 normal 用户请求模型列表、分类列表、实例统计和首页资产变更均返回 200。
2. 仅 `asset_info-View` 的 normal 用户得到相同结果。
3. 仅 `model_management-View` 的管理用户仍可读取模型和分类列表。
4. 无相关权限用户请求上述入口返回 403。
5. normal 用户调用模型 create、update、destroy 仍返回 403。
6. normal 用户调用通用操作日志 list 仍返回 403。
7. 首页资产变更 action 只返回允许的资产场景，分页上限不能由客户端绕过。
8. 模型列表和实例统计保留组织/对象权限裁剪。
9. Web 首页在 normal 权限下完成初始化，不出现 `/api/model` 及后续首页请求的 403。

后端先运行相关 View 定向测试，再运行 CMDB 最小回归；前端运行触及测试、`pnpm lint` 和 `pnpm type-check`。新增及修改代码覆盖率不低于 75%，权限和过滤分支目标不低于 90%。

## 7. 非目标

- 不给 normal 角色补发 `model_management-View` 或 `operation_log-View`。
- 不改变角色、菜单和权限表结构。
- 不重构通用 `HasPermission` 装饰器。
- 不改变模型、实例和操作日志的数据权限算法。
- 不处理与 CMDB 首页无关的其他页面权限问题。
