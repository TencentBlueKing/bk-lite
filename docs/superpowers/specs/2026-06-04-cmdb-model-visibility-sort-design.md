# CMDB 模型可见性与排序 设计文档

- 日期：2026-06-04
- 模块：CMDB（`server/apps/cmdb` + `web/src/app/cmdb`）
- 参考：监控中心 `MonitorObject` / `MonitorObjectType` 的可见性与排序能力

## 1. 背景与目标

监控中心对监控对象（type + object 两层）提供了「全局可见性开关」与「全局排序」能力，由管理员配置后所有用户看到一致的结果。CMDB 现在需要对等的能力：管理员可以隐藏不常用的模型/分类、调整菜单顺序，影响所有用户。

非目标：

- 不做按用户的个性化可见性/排序（用户级偏好不在本期范围）
- 不做模型跨分类拖拽（仅同分类内排序 + 分类整体排序）
- 不删除任何模型或数据；"隐藏"只是 UI 不可见，随时可恢复

## 2. 产品决策

| 维度 | 决策 |
|---|---|
| 生效范围 | **全局统一**：管理员配置一次，所有人看到一致 |
| 管控层级 | **分类 + 模型 两层**：分类可排序、可隐藏；模型在分类内可排序、可隐藏 |
| 隐藏语义 | 后端查询/接口层 + 前端统一过滤，前端全范围消失；数据保留，可随时恢复 |
| 配置入口 | 嵌入现有 `assetManage/management` 模型管理页，不另开页面 |
| 交互模式 | **管理模式**：开关进入编辑态，所有改动暂存，统一「保存/取消」 |
| 配置权限 | 沿用现有 `isSuperUser && selectedGroup.name === 'Default'` 门槛 |

## 3. 数据模型

写入图数据库节点属性，**不**使用 `UserPersonalConfig`。

| 实体 | 排序字段 | 可见性字段 |
|---|---|---|
| Model | `order_id`（已有，复用，默认 0） | **新增** `is_visible`（布尔，默认 `true`） |
| Classification | **新增** `order`（整数，默认 999） | **新增** `is_visible`（布尔，默认 `true`） |

实现要点：

- 通过现有 `set_entity_properties()` 写入，图库无固定 schema，**无需 schema 迁移**。
- **向后兼容**：读取时缺失值的处理
  - 缺失 `is_visible` → 视为 `true`（默认显示）
  - 缺失 classification `order` → 视为 999（排在已显式排序项之后）
  - 缺失 `order_id` → 视为 0（`search_model()` 已有此兜底）
- 旧数据无需批量初始化，第一次进入管理模式保存时自然落字段。

## 4. 后端 API

### 4.1 列表接口扩展 `include_hidden` 参数

| 接口 | 默认 | `?include_hidden=true` |
|---|---|---|
| `GET /cmdb/api/model/` | 仅 `is_visible=true`，按 `order_id` 升序 | 全部，附 `is_visible` + `order_id` |
| `GET /cmdb/api/classification/` | 仅 `is_visible=true`，按 `order` 升序 | 全部，附 `is_visible` + `order` |

约束：

- 过滤在 **service 层** 实现（`search_model()` / `search_model_classification()`），保证全部调用方一致。
- `search_model_classification()` 当前无显式排序，本次顺带加 `ORDER BY order ASC, classification_id ASC` 稳定排序。
- **`include_hidden=true` 仅对配置权限用户生效**；其他用户即使传也忽略。
- **单体查询不过滤**：`GET /cmdb/api/model/get_model_info/{model_id}/` 等按 ID 查单个模型/分类的接口**不**应用 `is_visible` 过滤——保证实例数据引用已隐藏模型时仍能解析模型名。

### 4.2 批量保存布局接口（新增）

```
POST /cmdb/api/model/save_layout/
```

请求体：

```json
{
  "classifications": [
    {"classification_id": "host",    "order": 0, "is_visible": true},
    {"classification_id": "network", "order": 1, "is_visible": false}
  ],
  "models": [
    {"model_id": "host_linux",   "order_id": 0, "is_visible": true},
    {"model_id": "host_windows", "order_id": 1, "is_visible": false}
  ]
}
```

语义：

- 客户端提交「完整目标状态」，后端在一个事务里把所有节点属性刷成目标值。
- **复用** 现有 `update_model_orders()`（位于 `services/model.py`），扩展为同时写 `is_visible`。
- **新增** `update_classification_layout()`（位于 `services/classification.py`）处理分类。
- 权限：DRF 层校验 `isSuperUser && Default` 组。
- 幂等：相同 payload 重复提交结果一致。
- 失败：事务回滚，返回错误；前端保留暂存状态供重试。

### 4.3 为什么不沿用监控中心的两个独立接口

监控中心是「切换即生效」，所以拆 `visibility/` + `order/` 两个独立接口合理。本设计采用「管理模式 + 保存/取消」，单接口批量提交更贴合：

- 客户端无需拼装两次调用、无需处理部分成功
- 「取消」回退路径简单（前端整批丢弃，后端无需引入回滚状态）

这是对方案 A 的自然延伸，是**有意偏离**监控中心的接口形态。

## 5. 前端实现

### 5.1 管理模式状态机（两栏布局）

在 `web/src/app/cmdb/(pages)/assetManage/management/page.tsx` 引入布尔状态 `manageMode`。进入管理态后，页面**原地切换为左右两栏布局**（参考监控中心对象页的交互），不另开路由：

| 项 | 浏览态（默认） | 管理态（两栏） |
|---|---|---|
| 布局 | 分类分组卡片栅格 | 左栏分类列表 + 右栏选中分类的模型表 |
| 数据源 | `CommonContext.modelList`（已过滤） | 本页独立拉取 `?include_hidden=true` |
| 入口按钮 | 「排序与可见性」 | 保存 / 取消 |
| 左栏（分类） | — | 可拖拽列表：拖拽手柄 + 名称(数量) + 眼睛开关；点击选中高亮；隐藏项半透明 |
| 右栏（模型） | — | 选中分类下的模型 `CustomTable`：行拖拽排序 + 可见性 `Switch` 列 |

进入管理态：

1. 并发调用 `GET /cmdb/api/model/?include_hidden=true` + `GET /cmdb/api/classification/?include_hidden=true`
2. 组装 `draftLayout`（暂存）+ `originalLayout`（快照），并默认选中第一个分类
3. 后续所有拖拽 / 切换只改 `draftLayout`，不调接口（仍保留**保存/取消**，不采用监控中心的「切换即生效」）

### 5.2 拖拽实现

**复用现有的 `@dnd-kit` 体系**（已是 web 包依赖，CMDB 模块内已有 `src/app/cmdb/components/sortable-item/` 封装）：

- 左栏分类用 `@dnd-kit` 可拖拽列表；右栏模型用 `CustomTable` 的 `rowDraggable`（与监控中心一致，CMDB 已在用）
- **本期不支持模型跨分类拖拽**——同分类内排序 + 分类整体排序即可
- 复用 `SortableItem` 组件减少样板代码

### 5.3 可见性切换 UI

- **分类（左栏）**：每行末尾加眼睛图标（`EyeOutlined` / `EyeInvisibleOutlined`），`stopPropagation` 避免触发选中；隐藏分类整行半透明。
- **模型（右栏表格）**：单独一列可见性 `Switch`（贴合监控中心）；隐藏模型行半透明。

### 5.4 保存 / 取消

- **保存**：调 `POST /cmdb/api/model/save_layout/` 提交完整 `draftLayout`；成功后退出管理态，调 `commonContext.refreshModelList()` 刷新全局共享的 `modelList`。
- **取消**：丢弃 `draftLayout`，退出管理态，恢复使用 `CommonContext.modelList`。
- **保存按钮启用条件**：`draftLayout` 与 `originalLayout` 有实质差异时启用，否则置灰。
- **未保存离开拦截**：管理态下用 Next.js 路由拦截 + `beforeunload` 弹确认框。

### 5.5 对全局 `CommonContext.modelList` 的影响

`modelList` 在整个 CMDB 应用层共享（实例列表、关联拓扑、搜索下拉等）。一旦后端默认列表接口开始过滤 `is_visible=false`，所有消费方自动获得"隐藏即不可见"的效果——这正是产品想要的。

**风险与缓解**：

- 风险：之前依赖"全量模型"做 `model_id → model_name` 映射的地方可能拿不到映射。
- 缓解：单体查询接口（`get_model_info/{model_id}/`）**不**过滤可见性（见 §4.1），实例数据引用已隐藏模型时仍能正确显示模型名，只是菜单/下拉不再有入口。

### 5.6 权限门控

管理态入口按钮的可见性沿用现有：

```ts
const showConfigButtons = isSuperUser && selectedGroup?.name === 'Default';
```

与现有「导出/导入模型配置」「公共枚举库管理」入口的权限模式保持一致。

## 6. 测试策略

### 后端

- `search_model()` / `search_model_classification()` 在 `include_hidden=false/true` 下的过滤与排序行为
- `save_layout/` 的原子性：构造一个会触发失败的子节点，校验事务回滚后所有节点属性都不变
- `save_layout/` 的幂等性：相同 payload 二次提交结果一致
- 权限：非超管 / 非 Default 组调用 `save_layout/` 与 `include_hidden=true` 时被正确拒绝
- 单体查询接口（`get_model_info/{model_id}/`）对已隐藏模型仍返回数据
- 向后兼容：缺失 `is_visible` / `order` / `order_id` 字段的旧节点在列表中正确呈现

### 前端

- 管理态进入 / 退出的状态切换
- 拖拽改动正确反映到 `draftLayout`，原数据不被污染
- 可见性切换 UI 反馈正确（半透明、标签）
- 保存按钮 enable 判定（无改动时置灰）
- 未保存离开拦截
- 保存成功后 `modelList` 全局刷新

## 7. 风险与未尽事项

- 实例详情等单体接口若漏改 `is_visible` 过滤豁免，会导致引用了已隐藏模型的实例显示异常——实施时需重点校验。
- 跨分类拖拽是常见后续需求，本期未支持；未来如需加入，需要扩展 `save_layout/` 的 payload 同时携带模型新的 `classification_id`。
- 大量分类/模型（>200）下拖拽性能未验证；如出现卡顿，再做虚拟化或仅在当前 viewport 内启用 sortable。

## 8. 文件改动清单（预期）

### 后端

- `server/apps/cmdb/services/model.py`：`search_model()` 增加 `include_hidden` 与 `is_visible` 过滤；`update_model_orders()` 扩展为也写 `is_visible`
- `server/apps/cmdb/services/classification.py`：`search_model_classification()` 增加 `include_hidden`、稳定排序；新增 `update_classification_layout()`
- `server/apps/cmdb/views/model.py`：新增 `save_layout` action；`list` 透传 `include_hidden`
- `server/apps/cmdb/views/classification.py`：`list` 透传 `include_hidden`
- 权限装饰器：新增 / 复用配置权限校验

### 前端

- `web/src/app/cmdb/(pages)/assetManage/management/page.tsx`：管理模式状态、拖拽、保存/取消、未保存拦截
- `web/src/app/cmdb/api/model.ts`：新增 `saveLayout()`；`getModelList()` 支持 `include_hidden` 参数
- `web/src/app/cmdb/api/classification.ts`：`getClassificationList()` 支持 `include_hidden`
- `web/src/app/cmdb/types/assetManage.ts`：`ModelItem` / `GroupItem` 增加 `is_visible`、分类 `order` 字段
- 可选：抽出 `ManageModeToolbar` / `SortableModelCard` 等子组件以保持页面文件可读
