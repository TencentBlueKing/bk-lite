# CMDB 机房机柜俯视图

> Migrated from `spec/requirements/CMDB/20260616.CMDB机房机柜俯视图.md` as legacy capability evidence.

## 1. 背景与问题

CMDB 已内置机房空间层级模型：`datacenter`（数据中心）── run 1:n ──> `server_room`（机房）── run 1:n ──> `rack`（机柜）── contains 1:n ──> `switch`/`router`/`firewall`/`loadbalance`/`physcial_server`（被装设备）。但目前只能在实例列表里逐条查看，**无法直观看到"机柜在机房哪一排哪一列""设备装在机柜第几 U"**。

经核查，机房平面图 / 机柜正视图在当前 codebase 中**不存在**：`rack` 无网格坐标字段、被装设备无 U 位字段，且无对应前端组件、接口与菜单入口。本需求新建该能力，交互逻辑对标实例详情已有的「网络拓扑」Tab（数据驱动、按需下钻、点击出详情）。

视觉与范围已确认：整套为 **2D**（不做 2.5D/等距，等距会把 U 位斜切读不清）；机房层为**俯视平面图**、机柜层为**正视 U 图**；状态颜色**仅取 CMDB 自有属性**，不接告警等外部模块；本期为**只读可视化**，不做网格拖拽编辑。

## 2. 需求项

### 2.1 数据模型字段（model_config.xlsx + 内置初始化）

1. `rack` 机柜模型新增 `row`（行，int）、`col`（列，int，前端渲染为 A–L 字母）。
2. `switch`/`router`/`firewall`/`loadbalance`/`physcial_server` 五个被装设备模型各新增 `rack_u_start`（起始 U 位，int）、`u_size`（占用 U 数，int）。
3. 全部走现有模型属性机制，自动复用实例表单 / 批量导入 / 详情展示；**不新增关联边属性**。

### 2.2 后端接口（apps/cmdb，对标 network_topo）

1. `GET .../room_layout/<server_room_id>/`：返回机房下所有机柜的 `inst_id/inst_name/row/col/u_count/datacenter_type/datacenter_state`，以及由其 `contains` 设备 `u_size` 汇总得出的 U 占用数 / 占用率。
2. `GET .../rack_layout/<rack_id>/`：返回机柜 `u_count` 及其 `contains` 设备列表（`inst_id/inst_name/model_id/rack_u_start/u_size` 及设备自有状态属性）。
3. 复用现有 `permission_map` 权限过滤、实例查询、关联查询逻辑；两接口均为只读。

### 2.3 前端展示（web/src/app/cmdb，2D，不引入 three.js）

1. **机房俯视平面图**：虚线网格（列 A–L × 行 1–N），机柜方块按 `row/col` 落格、按 `datacenter_type` 着色（普通/网络/存储/配电/配线/其他），方块显示 `u_count` + 机柜编号；空网格位显示 X 占位；支持缩放（含百分比）与平移；点机柜下钻。
2. **机柜正视 U 图**：按 `u_count` 画 U 槽，设备按 `rack_u_start/u_size` 精确排布，空 U 显示虚框；点设备打开现有实例详情抽屉。
3. **入口与导航**：CMDB 新增「机房视图」子页面作为主入口；`rack` 实例详情新增「机柜视图」Tab；面包屑三级导航（数据中心 / 机房 / 机柜）。

### 2.4 异常与边界处理

1. 设备未填 `rack_u_start`：归入正视图「未分配 U 位」区并提示补位，不静默丢弃。
2. U 位越界（超 `u_count`）或重叠：高亮冲突 U 段，给出运维友好可定位文案。
3. 机柜未填 `row/col`：归入平面图「未分配位置」列表提示补位，不静默丢弃。
4. 同格多柜：标记冲突提示。空机房 / 空机柜：友好空状态。

## 3. 验收口径

1. **字段生效**：五个设备模型可在实例表单填写 `rack_u_start/u_size`，`rack` 可填写 `row/col`，并随批量导入与详情展示。
2. **平面图**：进入某机房，机柜按 `row/col` 落格、按类型着色、显示 U 数与编号，空格为 X；缩放/平移可用；点机柜进入其正视图。
3. **正视图**：设备按 `rack_u_start/u_size` 排布正确，空 U 为虚框；点设备打开实例详情。
4. **下钻链路**：数据中心 → 机房 → 机柜 → 设备详情，面包屑可逐级回退。
5. **权限**：无权限的机柜/设备按现有权限规则过滤，不出现在平面图/正视图。
6. **异常**：未填 U 位的设备进入「未分配 U 位」区；U 位越界/重叠与机柜未填坐标均有明确提示而非静默丢弃。
7. **测试**：`room_layout`/`rack_layout` 服务层单测（占用率、未分配/越界/冲突、权限过滤）落入 `apps/cmdb/tests/` 并通过；前端布局纯函数（U→坐标、row/col→网格坐标、冲突检测）单测通过。

## 4. 约束与边界

**In Scope**

- `model_config.xlsx` 增量字段 + 内置初始化。
- `apps/cmdb` 新增 `room_layout` / `rack_layout` 两个只读接口。
- `web/src/app/cmdb` 新增机房平面图 / 机柜正视图组件、菜单入口、机柜详情 Tab。

**Out of Scope**

- 2.5D / 等距 / three.js 渲染。
- 网格拖拽编辑、机柜摆放/移动、点 X 新增机柜（本期只读，坐标在实例表单中维护）。
- 接入 `alerts` 等外部模块的实时健康/告警状态叠加。
- 关联边属性扩展；机柜内设备的精细布线 / 端口可视化。
