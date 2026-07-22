# Add Ops Analysis Room3D Screen Widget

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/add-ops-analysis-room3d-screen-widget/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

运营分析大屏已经具备固定分辨率 screen 画布、数据源取数、统一筛选、命名空间、组件刷新和组件配置能力。当前大屏可以展示折线、柱状、饼图、单值、表格、TopN、Gauge、事件表和轻量关系类组件，但缺少一种面向机房空间布局的可视化图表。

CMDB 已经沉淀了机房/机柜基础数据和机房机柜二维视图能力，包括：

- `server_room -> rack -> device` 关系；
- 机柜 `A03`、`B21` 这类 `字母 + 数字` 位置；
- 机柜类型、状态、U 数、已用 U、空闲 U、连续空闲 U；
- 位置格式错误、位置冲突、U 位冲突等数据质量语义；
- CMDB 实例权限过滤。

主流 DCIM/NOC 大屏通常会把 3D floor view 作为空间定位和展示组件嵌入大屏，而不是把完整 DCIM 管理能力塞进一个大屏组件。成熟产品会继续扩展 2D/3D 切换、rack elevation、温湿度、电力、告警、容量图层和下钻，但这些能力超出当前 MVP 范围。

本次变更目标是在不引入完整 DCIM 管理器的前提下，为运营分析 screen 大屏新增一个轻量、可复用、可接数据源的 `3D机房` 图表组件。第一版只做纯 3D 机房展示，不关联态势，不下钻，不编辑资产。

## What Changes

- 新增运营分析 screen 专用图表类型 `room3D`，中文展示为 `3D机房`。
- `room3D` 作为普通数据源图表进入大屏组件选择流程；只有数据源 `chart_type` 包含 `room3D` 时才可选择。
- 新增 CMDB NATS 数据源函数 `cmdb/get_room3d_layout`，用于把指定 `server_room_id` 的 CMDB 机房机柜数据转换为固定 `room3D` 数据契约。
- 在运营分析内置 `source_api.json` 中新增 `CMDB 3D机房布局` 数据源，初始化后可直接在 screen 大屏中选择使用。
- 新增前端 `Room3D` 渲染组件，接入现有 `WidgetWrapper` 取数、刷新、命名空间和组件错误状态链路。
- 大屏组件新增通用外观模式，支持将组件从默认面板外壳切换为无标题、无边框、无背景的画布直出模式；`room3D` 作为第一批验证组件。
- 第一版只支持在 screen 大屏中添加 `room3D` 组件，不开放到普通 dashboard。
- 第一版不提供字段映射和复杂展示配置，数据源必须返回固定字段契约。

## Capabilities

### New Capabilities

- `ops-analysis-room3d-screen-widget`: 运营分析 screen 大屏支持通过普通数据源添加 `3D机房` 图表组件，一个组件展示一个机房的 3D 机柜布局。
- `cmdb-room3d-layout-datasource`: CMDB 提供 `cmdb/get_room3d_layout` 数据源接口，将指定机房实例转换为 `room3D` 标准响应格式。

### Modified Capabilities

- `ops-analysis-screen-widget-types`: 大屏组件类型增加 `room3D`，但仅在数据源声明支持时展示。
- `ops-analysis-screen-widget-appearance`: 大屏组件配置增加 `appearance.frame=panel|bare`，用于控制 screen widget frame 的标题、边框和背景外壳。
- `ops-analysis-widget-data-validation`: 组件渲染层需要校验 `room3D` 数据契约，并对错误/空态给出组件级反馈。

## Impact

- **后端 CMDB**:
  - `server/apps/cmdb/nats/nats.py` 增加 `get_room3d_layout` NATS 数据源函数。
  - 复用 `server/apps/cmdb/services/rack_room.py` 的机房机柜布局能力和权限过滤逻辑。
  - 新增或扩展 CMDB 单测，覆盖正常、参数错误、非机房实例、权限过滤、空机房、位置格式诊断和位置冲突诊断。

- **后端运营分析**:
  - 继续复用 `/operation_analysis/api/data_source/get_source_data/{id}/` 取数链路。
  - 不新增独立 scene widget API。
  - 修改 `source_api.json` 做内置数据源初始化，降低首次试用成本。

- **前端运营分析**:
  - `web/src/app/ops-analysis/types/dataSource.ts` 增加 `room3D` chart type。
  - `web/src/app/ops-analysis/types/screen.ts` 增加 `room3D` screen widget chart type。
  - `web/src/app/ops-analysis/components/widgetRegistry.ts` 注册 `Room3D` 组件。
  - 组件选择、配置和渲染需要支持 `room3D`，展示后端返回的 `notice`，并在前端聚合同坐标机柜为红色外框冲突态，但第一版不新增专属字段映射配置。

- **不在本次范围**:
  - 不做 2D/3D 切换。
  - 不做 rack elevation / U 位设备明细。
  - 不做告警、温湿度、电力、容量热力等态势图层。
  - 不做机柜编辑、拖拽上架、CMDB 资产写入。
  - 不做点击跳转、双击下钻、外部链接。
  - 不做多机房切换；一个组件只展示一个机房。
  - 不开放到普通 dashboard。

## Implementation Decisions

## Context

运营分析的 screen 画布定位是固定分辨率大屏展示和汇报画布。当前 screen 已经复用 dashboard 的数据源配置、组件取数、图表渲染、统一筛选和命名空间能力，并通过 `ScreenWidgetRenderer -> WidgetWrapper -> WidgetRenderer -> widgetRegistry` 渲染具体组件。

CMDB 当前已有机房机柜能力：

- 后端 `apps.cmdb.services.rack_room` 提供 `get_room_layout` 和 `get_rack_layout`；
- 机房布局使用 `server_room` 下关联的 `rack` 实例；
- CMDB 资产列表中的机柜 `location`（中文名：位置）以 `A03`、`B21` 这类 `字母 + 数字` 格式表达；
- 字母段表示行，数字段表示列，转换到 room3D 契约后仍是 1-based `row/col` 网格；
- 后端负责把 CMDB `location` 解析为标准位置和 `row/col`，位置格式错误的机柜不进入 `racks`，通过可选 `notice` 暴露；坐标冲突属于通用 `row/col` 展示问题，由前端按相同坐标聚合并渲染红色外框冲突提示。

本次设计让 `3D机房` 成为运营分析 screen 里的普通数据源图表，而不是独立 scene widget API，也不是 CMDB 详情页的 3D 替代品。

## Goals / Non-Goals

**Goals:**

- 在 screen 大屏中新增 `room3D` 图表类型。
- 让用户通过内置数据源初始化获得可用的 `CMDB 3D机房布局` 数据源。
- 一个 `room3D` 组件展示一个机房，通过 `server_room_id` 参数指定。
- 新增 CMDB 数据源接口，将 CMDB 机房机柜数据转为固定 `room3D` 响应契约。
- 前端组件按固定契约渲染 3D 鸟瞰机房、机柜网格、类型颜色、图例、hover tooltip 和 click 信息浮层。
- 保持第一版配置轻量：不做字段映射，不暴露视角、材质、自动旋转等专属配置。
- 对数据格式、权限、空态和机柜级数据问题给出明确反馈；房间级错误阻断展示，机柜级位置问题不阻断其他有效机柜渲染。

**Non-Goals:**

- 不实现完整 DCIM 管理器。
- 不支持多机房切换或一个组件展示多个机房。
- 不支持态势数据源、告警/温湿度/电力/容量图层。
- 不支持完整 rack elevation 管理、设备下钻或跳转。
- 不支持在 `room3D` 内编辑设备上架位置、U 位占用或机柜资产。
- 不支持 2D/3D 切换。
- 不支持在 `room3D` 组件里编辑 CMDB 资产、机柜位置或设备上架关系。
- 不开放到普通 dashboard。

## Decisions

### D1: `room3D` 是普通数据源图表，不是独立场景组件

**决策**: `room3D` 走现有数据源图表链路。用户在 screen 中添加组件时，选择支持 `room3D` 的数据源，再选择 `3D机房` 图表类型。

**理由**:

- 用户目标是“运营分析里一种可复用的大屏图表”。
- 第一版不关联态势、不下钻、不编辑，不需要独立 scene widget API。
- 现有 `WidgetWrapper` 已提供数据源参数、统一筛选、命名空间、刷新、缓存和组件级错误状态。
- 如果第一版做成特殊 scene widget，会过早引入 CMDB 场景页心智和复杂配置。

### D2: 只支持 screen，不开放 dashboard

**决策**: 第一版 `room3D` 只允许添加到 screen 大屏。

**理由**:

- 需求明确是“大屏组件”。
- 3D 机房需要较稳定的容器尺寸，dashboard 卡片尺寸和信息密度更难保证。
- 先在固定分辨率 screen 中验证数据契约、渲染性能和视觉可读性。

### D3: 严格依赖数据源 `chart_type` 声明

**决策**: 只有数据源 `chart_type` 包含 `room3D` 时，组件选择器和配置抽屉才展示 `3D机房` 类型。

**理由**:

- `room3D` 需要固定空间数据契约，不适合让任意表格数据源试配。
- 数据源声明支持后，表示它承诺返回 `room + racks + notice?` 结构。
- 这样可以减少字段映射和错误试错成本。

### D4: 固定响应契约，不做字段映射

**决策**: `room3D` 第一版只支持一种响应格式：

```json
{
  "room": {
    "id": "7",
    "name": "一号机房"
  },
  "racks": [
    {
      "rack_id": "5",
      "rack_name": "A03",
      "row": 1,
      "col": 3,
      "location": "A03",
      "rack_type": "network",
      "u_count": 42,
      "used_u": 21,
      "free_u": 21,
      "device_count": 8
    }
  ]
}
```

必填字段：

- `room.id`
- `room.name`
- `racks`
- `rack_id`
- `rack_name`
- `row`
- `col`

可选字段：

- `location`
- `rack_type`
- `u_count`
- `used_u`
- `free_u`
- `device_count`

不兼容裸数组、`items` 包装、设备嵌套和自定义字段名。

**理由**:

- 第一版要轻，不把配置抽屉做成字段映射工具。
- 既然数据源声明支持 `room3D`，就应该按组件契约返回数据。
- 固定契约更利于测试、错误提示和后续扩展。

### D5: 一个组件展示一个机房

**决策**: `cmdb/get_room3d_layout` 通过 `server_room_id` 参数返回单个机房。

**理由**:

- 主流 3D floor view 通常展示一个 room/floor；多机房由 dashboard/NOC 层编排。
- 多机房会引入房间切换、比例、排布、轮播等额外产品问题。
- screen 可以通过多个 `room3D` 组件展示多个机房。

### D6: 坐标语义沿用 CMDB 位置字段

**决策**:

- `row` / `col` 都是 1-based。
- CMDB `location` 的字母段解析为 `row`，数字段解析为 `col`，例如 `A03` 和 `A3` 都解析为 `row=1, col=3`。
- 前端空间映射保持 `col -> X`、`row -> Z`。
- 机柜顶部、tooltip 和详情展示标准位置字符串，优先使用后端 `location`，例如 `A01`、`A02`、`A03`、`A04`、`B03`，不展示 `C列 / 1行` 这类派生文案。
- 多个机柜共享同一个 `row + col` 时，接口仍返回这些机柜；前端聚合为一个普通机柜材质的冲突机柜，并叠加稍粗红色外框，详情展示冲突机柜列表，柜门不可点击打开。

**理由**:

- 与现有 CMDB 资产列表的“位置”字段一致，避免用机柜名反推坐标。
- 比暴露 3D `x/y/z` 坐标更适合运维用户和 MVP 接入。
- 坐标冲突是通用空间数据问题，放在前端聚合展示可以降低后续其他 API 接入约束。
- 后续如需支持不规则机房、旋转、实际米制坐标，可在新字段中扩展。

### D7: CMDB 接口复用现有权限与布局服务

**决策**: 新增 `cmdb/get_room3d_layout` NATS 函数，复用 `apps.cmdb.services.rack_room` 的机房布局组装和权限过滤逻辑。

参数：

```json
{
  "server_room_id": 7
}
```

返回：

```json
{
  "result": true,
  "data": {
    "room": {
      "id": "7",
      "name": "一号机房"
    },
    "racks": []
  },
  "message": ""
}
```

房间级错误：

- 缺少 `server_room_id`：`result=false`，参数错误。
- `server_room_id` 非法：`result=false`，参数错误。
- 实例不存在：`result=false`，不存在。
- 实例不是 `server_room`：`result=false`，参数错误。
- 用户无机房查看权限：`result=false`，无权限。

机柜级提示：

- 机柜 `location` 为空或不是 `字母 + 数字` 格式：该机柜不进入 `racks`，后端在 `data.notice` 返回一条可直接展示的汇总提示。
- 多个机柜解析出相同 `row/col`：后端不判定冲突、不过滤机柜，全部进入 `racks`；前端按 `row/col` 聚合为带稍粗红色外框的冲突机柜。
- 非冲突且位置格式正确的机柜继续进入 `racks` 并正常渲染。
- 后端只返回必要的业务提示字符串，前端负责通用空间冲突展示，不再消费 `diagnostics` 结构。

**理由**:

- 仍通过运营分析数据源取数，不给前端单独加 CMDB hook。
- 不绕过 CMDB 权限。
- 通过内置数据源降低首次测试成本，并继续复用运营分析数据源取数链路。

### D8: 第一版配置项尽量为零

**决策**: 除现有数据源选择和参数配置外，`room3D` 第一版不新增专属展示配置。

默认行为：

- 固定等距鸟瞰视角。
- 自动适配组件容器。
- 支持鼠标缩放、旋转、平移。
- 支持重置视角。
- hover 显示机柜名称和行列位置。
- click 固定选中机柜并显示轻量信息浮层。
- 坐标冲突机柜保持正常机柜材质，叠加稍粗红色外框，点击后只展示冲突详情，不打开柜门、不展示设备层。
- 机柜按 `rack_type` 默认着色。
- 显示图例。
- 标签默认开启，但组件过小时自动隐藏。
- 自动旋转默认关闭，不暴露配置。

**理由**:

- 第一版目标是验证可复用图表和数据契约。
- 复杂配置会把 MVP 做重，也增加验收面。
- 默认值足以满足大屏展示。

### D9: 大屏组件外壳做成通用外观模式

**决策**: 在 screen 组件配置中增加通用 `appearance.frame` 字段，取值固定为 `panel` 或 `bare`。`panel` 保持当前标题、边框、角标和半透明背景；`bare` 去掉标题、边框、角标和背景，让组件内容直接显示在大屏画布上。

第一版规则：

- 未配置 `appearance.frame` 的存量组件按 `panel` 渲染。
- 新增 `room3D` 组件默认使用 `bare`，更贴近 3D 场景展示。
- 其他组件默认仍使用 `panel`，但用户可以在 screen 配置抽屉中切换为 `bare`。
- `bare` 只影响 screen 外层 frame，不改变 `WidgetWrapper` 取数、统一筛选、命名空间、刷新和错误状态链路。
- `bare` 查看态不显示标题、边框、角标、背景和操作噪音。
- `bare` 编辑态仍保留轻量选中轮廓、拖拽热区和右上角更多操作，确保组件可以移动、配置和删除。
- `room3D` 组件内部的重置视角、图例、hover/click 浮层保留。
- `room3D` 在 `bare` 外观下进入透明沉浸态：Three 场景不绘制深色背景和深色地板，组件根节点透明，房间标题、重置视角按钮和图例默认隐藏，鼠标进入组件或组件内部聚焦时再显示。

**理由**:

- 需求本质是大屏组件 chrome 能力，不是 `room3D` 私有样式。
- screen 设计原则要求大屏不能直接套用 dashboard 普通卡片外观。
- 两档模式足以覆盖第一版诉求，避免过早引入标题位置、边框透明度、背景色等细粒度配置。

### D10: 第二阶段增强采用轻量拟真，不引入重型模型资产

**决策**: `room3D` 第二阶段将展示升级为参考图式拟真机房：浅色地砖、长方形低墙围合、嵌入式主入口大门、默认视角下方近墙可见的大门、少量后墙门窗、粗白结构柱、后墙左侧成组电箱/设备柜、深灰金属机柜、柜门网孔、内部设备层、选中描边、必要时开门聚焦、设备抽出和右侧设备详情浮层。房间围合应优先呈现长方形，目标宽深比约 1.35-1.45，长边跟随机柜矩阵主方向形成真实机房的主通道感，避免单排机柜落在近似正方形空场中。可见大门必须具备中性灰蓝门洞、厚门框、双开门板、中缝、窄玻璃窗、把手和窄门槛等入口识别特征，不能只是贴在墙面的浅色矩形；大门前后两面都应具备门板、玻璃、把手和门缝效果。机房以高环境光为主，墙面附件和柱体不应在地面产生孤立硬投影，门槛应表现为窄压条而不是平台。房间装饰应克制，优先用墙体/柱体/门洞形成空间体块感，避免堆叠零散小物件抢占真实机柜数据展示。实现方式仍使用 Three 基础几何体、材质和少量 canvas 贴图，不引入 GLTF/FBX 模型流水线，也不复用参考项目的大插件实现。

**理由**:

- 用户目标是运营分析中可复用的大屏图表组件，不是完整 3D 建模器。
- 参考系统的 `3d-idc` 证明主流交互包括房间、机柜、选中描边、点击开柜门和信息浮层，但其插件式压缩实现不适合直接迁入当前 Next/React 组件。
- 基础几何体可以在第一版保持较低依赖、较小包体和可测试的数据映射，同时达到足够真实的演示效果。
- 机柜间距需要为开门和设备抽出留出观察空间；相机只在当前距离过远时自动靠近，避免用户已经看清机柜时画面仍反复旋转或缩放。

### D11: 机柜内设备明细作为可选展示数据

**决策**: 在固定响应契约中新增可选 `racks[].devices`。后端复用 CMDB 现有 `rack_room.get_rack_layout` 的 U 位口径，只返回具备真实 `rack_u_start` 和 `u_size` 的已上架设备。没有 U 位的设备不进入 3D 设备层，只通过 `unplaced_device_count` 暴露数量。前端不根据 `device_count` 生成占位设备，也不猜测 U 位。打开机柜后点击真实设备层时，设备向外抽出，并在组件右侧展示只读设备详情。

**理由**:

- CMDB 已有 `rack_u_start` 和 `u_size`，能支撑“打开柜门看到设备”的只读展示。
- 设备明细必须可定位才渲染，避免前端制造不存在的设备或错误 U 位。
- `device_count` 保持当前用户可见设备总数口径，`unplaced_device_count` 用于提示数据未完整上架。

### D12: 前端拆分以控制复杂度

**决策**: 将当前 `room3D/index.tsx` 中的 Three 场景构建拆为同目录小模块：

- `room3DData.ts`：数据契约、校验、设备归一化和展示兜底。
- `room3DScene.ts`：场景、灯光、相机、控制器、resize 和渲染循环。
- `room3DMeshes.ts`：房间、地砖、主入口大门、结构柱、靠墙设备柜、机柜、柜门、设备层等几何体工厂。
- `index.tsx`：React 状态、数据校验、hover/click 信息浮层和生命周期衔接。

**理由**:

- 当前组件已经承担数据、场景、交互和 UI 四类职责，继续堆叠会降低可维护性。
- 拆分按职责而不是按技术层，能让 Three 资源释放、交互拾取和数据契约各自可读。
- 不引入过度抽象，仍保持 `room3D` 为一个独立组件目录。

## Data Contract

### 请求参数

`cmdb/get_room3d_layout` 支持一个参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `server_room_id` | string/number | 是 | CMDB `server_room` 实例 ID，后端转整数校验 |

### 响应数据

数据源最终返回给前端的 `data` 必须是：

```ts
interface Room3DResponse {
  room: {
    id: string;
    name: string;
  };
  racks: Room3DRack[];
  notice?: string;
}

interface Room3DRack {
  rack_id: string;
  rack_name: string;
  row: number;
  col: number;
  location?: string;
  rack_type?: string | null;
  u_count?: number;
  used_u?: number;
  free_u?: number;
  device_count?: number;
  unplaced_device_count?: number;
  devices?: Room3DDevice[];
}

interface Room3DDevice {
  device_id: string;
  device_name: string;
  model_id?: string | null;
  rack_u_start: number;
  u_size: number;
  status?: string | null;
}
```

### CMDB 字段映射

| `room3D` 字段 | CMDB 来源 |
| --- | --- |
| `room.id` | `server_room` 实例 ID |
| `room.name` | `server_room.inst_name` |
| `rack_id` | `rack.inst_id` |
| `rack_name` | `rack.inst_name` |
| `row` | 由 `rack.location` 的字母段解析，`A03 -> 1`、`B21 -> 2` |
| `col` | 由 `rack.location` 的数字段解析，`A03 -> 3`、`B21 -> 21` |
| `location` | 标准化后的机柜位置，`A3 -> A03`、`B21 -> B21` |
| `rack_type` | `rack.datacenter_type` |
| `u_count` | `rack.u_count` |
| `used_u` | `rack.used_u` |
| `free_u` | `rack.free_u` |
| `device_count` | 当前用户可见的机柜直接关联设备数量，不要求设备具备有效 U 位 |
| `unplaced_device_count` | 当前用户可见但缺少有效 U 位、无法在 3D 柜内定位的设备数量 |
| `devices[].device_id` | 机柜直接关联设备实例 ID |
| `devices[].device_name` | 机柜直接关联设备 `inst_name` |
| `devices[].model_id` | 机柜直接关联设备 `model_id` |
| `devices[].rack_u_start` | 设备 `rack_u_start` |
| `devices[].u_size` | 设备 `u_size` |
| `devices[].status` | 设备可识别状态字段，第一版无稳定字段时可为空 |
| `notice` | 可选提示文本，用于后端发现部分机柜位置格式错误等业务提示 |

## UI Flow

### 数据源初始化

系统通过 `source_api.json` 初始化内置数据源：

- 名称：`CMDB 3D机房布局`
- REST API：`cmdb/get_room3d_layout`
- 图表类型：`room3D`
- 参数：
  - `server_room_id`
  - 类型：string 或 number
  - 默认值：空
  - `filterType`: `params`

初始化后，用户在 screen 大屏添加组件时直接选择该数据源，并填写 `server_room_id` 参数。

### 大屏添加组件

1. 进入运营分析 screen 大屏编辑态。
2. 添加组件。
3. 选择 `CMDB 3D机房布局` 数据源。
4. 选择图表类型 `3D机房`。
5. 填写 `server_room_id` 参数。
6. 保存组件。
7. screen 组件通过 `WidgetWrapper` 取数并渲染 3D 机房。

## Error Handling

### 后端

- 无权限机柜不进入 `racks`，保持与 CMDB 权限过滤一致。
- 机房无机柜时返回 `room + racks: []`。
- 机柜 `location` 只接受 `字母 + 数字` 格式，例如 `A3`、`A03`、`B21`；无法解析的机柜不进入 `racks`，后端在 `data.notice` 返回可直接展示的提示，不使用旧 `row/col` 兜底。
- 解析后的机柜位置冲突不在后端过滤；冲突机柜仍进入 `racks`，由前端按 `row/col` 聚合成一个带稍粗红色外框的冲突机柜。
- 只要房间级校验通过，后端仍返回 `result=true` 和可渲染 `racks`；所有机柜均不可解析时也返回 `result=true`，由前端展示空态和后端 `notice`。
- 业务提示由后端生成，前端不重复判断 CMDB `location` 格式或拼接业务文案。

### 前端

- 缺少 `room` 或 `racks`：组件错误态，提示 `3D机房数据格式错误`。
- `racks` 不是数组：组件错误态。
- 某条机柜缺少 `rack_id/rack_name/row/col`：组件错误态。
- `row/col < 1`：组件错误态。
- `racks` 为空且无 `notice`：空态，提示 `暂无机柜布局数据`。
- `notice` 非空：展示后端返回的提示文本；不阻断有效机柜渲染。
- 多个机柜 `row/col` 相同：前端聚合为一个普通机柜材质的冲突机柜，叠加稍粗红色外框，点击展示冲突机柜列表，柜门不可打开。
- 取数失败：复用现有 `WidgetErrorState`。
- 渲染失败只影响当前组件，不影响其他大屏组件。

## Risks / Trade-offs

| 风险 | 缓解措施 |
| --- | --- |
| 3D 组件性能影响大屏 | 第一版只渲染机柜层，不渲染设备明细、热力图或复杂材质；组件卸载时释放 3D 资源 |
| 固定契约降低自定义数据源灵活性 | 第一版优先轻量和稳定；后续可在确认需求后增加字段映射 |
| 只支持单机房可能被误解为能力不足 | 明确一个组件一个机房，多机房通过 screen 编排多个组件解决 |
| 机柜位置问题导致部分数据无法展示 | 位置格式错误由后端返回 `notice`，有效机柜继续渲染；位置冲突由前端红框暴露，避免单个脏数据清空整个房间 |
| 内置数据源可能增加默认列表噪声 | 该数据源挂 `cmdb` 标签，且只有 `chart_type=room3D`，只在 screen 场景中形成有效选择 |

## Verification

- 后端单测覆盖 CMDB `get_room3d_layout` 正常、参数错误、非机房实例、权限过滤、空机房、位置格式错误进入 notice、位置冲突继续返回、有效机柜继续返回。
- 前端测试覆盖 `room3D` 数据契约校验、空态、错误态、notice、位置冲突聚合和 chart type 可选条件。
- 手动验证初始化内置数据源后，screen 大屏能添加 `3D机房` 组件并展示指定机房。
- 运行对应模块质量门禁：
  - 后端改动：`cd server && make test` 或目标 CMDB/operation_analysis 单测。
  - 前端改动：`cd web && pnpm lint && pnpm type-check`。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-07-06
```

## Capability Deltas

### ops-analysis-room3d-screen-widget

## ADDED Requirements

### Requirement: Screen MUST support a CMDB room3D chart type

运营分析大屏 SHALL 支持 `room3D` 图表类型，并且只在数据源声明 `chart_type` 包含 `room3D` 时允许选择该图表类型。

#### Scenario: Add room3D from a supported data source

- **Given** 数据源 `chart_type` 包含 `room3D`
- **When** 用户在 screen 大屏中添加组件
- **Then** 图表类型选择中应展示 `3D机房`
- **And** 组件应继续通过 `WidgetWrapper` 取数

#### Scenario: Hide room3D for unsupported data sources

- **Given** 数据源 `chart_type` 不包含 `room3D`
- **When** 用户在 screen 大屏中选择该数据源
- **Then** 图表类型选择中不应展示 `3D机房`

### Requirement: CMDB room3D data source MUST return one room layout

系统 SHALL 提供 `cmdb/get_room3d_layout` 数据源接口，通过 `server_room_id` 返回单个 CMDB 机房的 `room + racks + notice?` 固定契约，并复用 CMDB 权限与机柜布局口径。

#### Scenario: Return room and rack contract

- **Given** 用户有权限查看指定 `server_room`
- **And** 该机房下存在已定位机柜
- **When** 数据源调用 `cmdb/get_room3d_layout`
- **Then** 响应数据应包含 `room.id`、`room.name` 和 `racks`
- **And** 每个机柜应包含 `rack_id`、`rack_name`、`row`、`col` 和标准位置 `location`
- **And** `row`、`col` 应由 CMDB 机柜 `location` 字段按 `A3`、`A03`、`B21` 格式解析而来，其中字母段表示行、数字段表示列

#### Scenario: Report invalid rack location without blocking valid racks

- **Given** 机柜 `location` 不是 `字母 + 数字` 格式
- **And** 同一机房存在其他位置合法且不冲突的机柜
- **When** 数据源调用 `cmdb/get_room3d_layout`
- **Then** 系统应返回成功
- **And** 位置合法的机柜应进入 `racks`
- **And** 位置非法的机柜不应进入 `racks`
- **And** `data.notice` 应包含后端生成的汇总提示，可直接展示给用户

#### Scenario: Return rack devices when available

- **Given** 机柜存在当前用户可见的直接关联设备
- **When** 数据源调用 `cmdb/get_room3d_layout`
- **Then** 对应机柜应包含具备真实 U 位的 `devices`
- **And** 每个设备应包含 `device_id`、`device_name`、`model_id`、`rack_u_start`、`u_size` 和 `status`
- **And** 缺少有效 U 位的设备不应进入 `devices`

#### Scenario: Report conflicting rack locations without blocking non-conflicting racks

- **Given** 同一机房中多个机柜解析出相同 `row` 和 `col`
- **And** 同一机房存在其他位置合法且不冲突的机柜
- **When** 数据源调用 `cmdb/get_room3d_layout`
- **Then** 系统应返回成功
- **And** 冲突机柜和非冲突机柜均应进入 `racks`
- **And** 接口不应返回 `diagnostics.conflicts`

#### Scenario: Frontend displays backend notice and coordinate conflicts

- **Given** 数据源响应包含 `notice`
- **When** `room3D` 组件渲染
- **Then** 组件应展示后端返回的提示文本

- **Given** 数据源响应中多个机柜包含相同 `row` 和 `col`
- **When** `room3D` 组件渲染
- **Then** 组件应在该坐标渲染一个普通机柜材质的冲突机柜，并叠加稍粗红色外框
- **And** 冲突机柜顶部、tooltip 和详情应展示标准位置，例如 `A03`
- **And** 点击冲突机柜应展示冲突机柜列表
- **And** 冲突机柜柜门不应打开，也不应展示设备层

### Requirement: Screen widgets SHOULD support panel and bare frame appearance

screen 组件 SHALL 支持通用 `appearance.frame` 外观配置，取值为 `panel` 或 `bare`。`room3D` 新增组件默认使用 `bare`，其他组件默认使用 `panel`。

#### Scenario: room3D defaults to bare frame

- **Given** 用户新增 `room3D` screen 组件
- **When** 系统创建组件配置
- **Then** 组件 `valueConfig.appearance.frame` 应默认为 `bare`

#### Scenario: Bare frame removes canvas chrome in view mode

- **Given** screen 组件配置为 `appearance.frame = bare`
- **When** 用户查看大屏
- **Then** 组件外层不应展示默认标题、边框、角标和背景
- **And** 组件仍应保留编辑态选中、拖拽、配置和删除能力

### Requirement: room3D SHOULD render a lightweight realistic room and rack scene

`room3D` 组件 SHALL 使用轻量 Three 几何体渲染参考图式拟真机房，包括浅色地砖、长方形拟真墙面、嵌入式主入口大门、默认视角下方近墙可见的大门、少量后墙门窗、粗白结构柱、后墙左侧成组电箱/设备柜、灰色金属机柜、柜门网孔、U 位刻度、设备层、选中描边、信息浮层和重置视角。

#### Scenario: Render realistic room shell and racks

- **Given** `room3D` 数据包含已定位机柜
- **When** 组件渲染成功
- **Then** 3D 场景应展示浅色地砖、与机柜接近等高且非透明感过强的纹理墙面和机柜
- **And** 机柜应展示为可看清内部设备层的灰色金属柜体
- **And** 机柜列距应保持矩阵可读，排距应明显拉开以支持站在柜前查看设备
- **And** 墙面应包含嵌入式主入口大门、默认视角下方近墙可见的大门、少量门窗、门窗框、角柱和粗白结构柱
- **And** 可见大门应包含中性灰蓝门洞、厚门框、双开门板、中缝、窄玻璃窗、把手和窄门槛，不能表现为浅色墙板或突出平台
- **And** 可见大门前后两面都应具备门板、玻璃、把手和门缝效果
- **And** 墙面附件和柱体不应在地面产生孤立硬投影
- **And** 机房后墙左侧可展示少量成组配电柜或设备柜类静态设施，用于增强空间真实感，但不应抢占真实机柜数据展示
- **And** 墙面围合范围应明显大于机柜矩阵，避免遮挡机柜主体视图
- **And** 房间围合应优先呈现长方形，目标宽深比约 1.35-1.45，长边跟随机柜矩阵主方向
- **And** 机柜正面应展示 U 位刻度

#### Scenario: Click rack opens cabinet door and shows rack info

- **Given** `room3D` 场景中存在机柜
- **And** 该机柜没有坐标冲突
- **When** 用户点击某个机柜
- **Then** 该机柜应显示选中描边
- **And** 该机柜柜门应打开
- **And** 组件应展示该机柜的信息浮层
- **And** 若当前视角已经能看清该机柜，视角不应自动旋转或缩放
- **And** 若当前视角距离该机柜过远，视角才应自动靠近并定位到该机柜
- **When** 用户点击非机柜空白区域
- **Then** 已打开柜门应保持打开
- **And** 已选中机柜信息应保持展示
- **When** 用户再次点击已选中机柜的柜门
- **Then** 该机柜柜门应关闭

#### Scenario: Render device layers from real data only

- **Given** 机柜数据包含 `devices`
- **When** 用户打开该机柜
- **Then** 机柜内部设备层应按 `devices` 的真实 U 位信息展示

- **Given** 机柜数据不包含 `devices` 但包含 `device_count`
- **When** 用户打开该机柜
- **Then** 组件不应生成占位设备层
- **And** 机柜信息可展示 `device_count` 或 `unplaced_device_count` 暴露数据未完整上架

#### Scenario: Select a device inside an opened rack

- **Given** 用户已打开包含设备层的机柜
- **When** 用户点击某个设备层
- **Then** 该设备层应短距离向机柜外侧抽出，保持仍属于机柜内部设备的视觉关系
- **And** 组件右侧应展示设备详情浮层
- **And** 设备详情应至少展示设备名称、所在机柜、模型、U 位、高度和状态
- **When** 用户再次点击同一个已抽出的设备层
- **Then** 该设备层应弹回机柜内部
- **And** 设备详情浮层应关闭

#### Scenario: Open rack absorbs empty interior clicks

- **Given** 用户已打开某个机柜
- **When** 用户点击该机柜内部空白区域
- **Then** 点击不应穿透到后方机柜
- **And** 后方机柜柜门不应被打开

#### Scenario: Bare room3D keeps transparent scene background

- **Given** `room3D` 组件配置为 `appearance.frame = bare`
- **When** 组件渲染 3D 场景
- **Then** WebGL 清屏背景应为透明
- **And** 房间地面和墙体自身仍应正常可见

## Work Checklist

## 1. CMDB 数据源接口

- [x] 1.1 在 `server/apps/cmdb/nats/nats.py` 中新增 `get_room3d_layout(server_room_id, user_info=None, **kwargs)`。
- [x] 1.2 校验 `server_room_id` 必填且可转为整数。
- [x] 1.3 查询实例并校验实例存在且 `model_id == "server_room"`。
- [x] 1.4 复用 CMDB 实例查看权限，用户无机房权限时返回无权限错误。
- [x] 1.5 复用 `apps.cmdb.services.rack_room.get_room_layout` 获取机柜布局，并保持机柜权限过滤。
- [x] 1.6 将 CMDB 机房布局转换为固定 `room3D` 契约：`room + racks + notice?`。
- [x] 1.7 计算并返回 `device_count`，口径固定为“当前用户可见的机柜直接关联设备数量”，不要求设备具备有效 U 位。
- [x] 1.8 机柜位置格式错误时，不返回房间级失败；后端跳过不可解析机柜并通过 `data.notice` 返回一条可展示提示。
- [x] 1.9 位置冲突不由后端过滤，解析成功的机柜全部进入 `racks`，由前端按 `row/col` 聚合展示红色外框冲突提示。
- [x] 1.10 空机房返回 `room + racks: []`，不视为错误。

## 2. 后端测试

- [x] 2.1 为 `get_room3d_layout` 增加正常返回测试，断言 `room` 和 `racks` 字段契约。
- [x] 2.2 测试缺少 `server_room_id` 返回参数错误。
- [x] 2.3 测试非法 `server_room_id` 返回参数错误。
- [x] 2.4 测试实例不存在返回不存在错误。
- [x] 2.5 测试实例不是 `server_room` 返回参数错误。
- [x] 2.6 测试无权限机房返回无权限错误。
- [x] 2.7 测试无权限机柜被过滤，不进入 `racks`。
- [x] 2.8 测试空机房返回空 `racks`。
- [x] 2.9 测试同一 `row/col` 多机柜全部进入 `racks`，留给前端通用冲突展示处理。
- [x] 2.10 测试非法或空 `location` 被跳过，合法机柜继续返回，`data.notice` 包含后端生成提示。
- [x] 2.11 测试成功响应不再包含 `diagnostics` 结构。

## 3. 前端类型与图表注册

- [x] 3.1 在 `web/src/app/ops-analysis/types/dataSource.ts` 的 `ChartType` 中增加 `room3D`。
- [x] 3.2 在 `web/src/app/ops-analysis/types/screen.ts` 的 `ScreenWidgetChartType` 中增加 `room3D`。
- [x] 3.3 新增 `Room3D` 组件类型定义和数据契约类型。
- [x] 3.4 在 `web/src/app/ops-analysis/components/widgetRegistry.ts` 注册 `room3D -> Room3D`。
- [x] 3.5 确保 `room3D` 只在 screen 添加组件流程中可用，不开放到普通 dashboard。

## 4. 前端 Room3D 渲染组件

- [x] 4.1 新增 `web/src/app/ops-analysis/components/widgets/room3D/` 组件目录。
- [x] 4.2 实现 `room3D` 响应契约校验：`room`、`racks`、`rack_id`、`rack_name`、`row`、`col`。
- [x] 4.3 实现空态：`racks` 为空时显示“暂无机柜布局数据”。
- [x] 4.4 实现错误态：格式错误、非法坐标、渲染失败时显示组件级错误。
- [x] 4.5 实现 3D 地板网格和机柜矩阵渲染，`col -> X`、`row -> Z`。
- [x] 4.6 实现机柜类型默认着色和图例。
- [x] 4.7 实现 hover tooltip，展示机柜名称和位置。
- [x] 4.8 实现 click 选中机柜和轻量信息浮层。
- [x] 4.9 实现点击空白处取消选中。
- [x] 4.10 实现缩放、旋转、平移和重置视角。
- [x] 4.11 组件卸载时释放 3D 资源，避免大屏切换后残留监听或 WebGL 资源。
- [x] 4.12 展示后端返回的 `notice`，前端不重新判断 CMDB `location` 格式或拼接业务错误文案。
- [x] 4.13 前端按 `row/col` 聚合位置冲突，渲染正常机柜材质 + 稍粗红色外框，详情展示冲突机柜列表，柜门不可点击打开。
- [x] 4.14 机柜顶部、tooltip 和详情统一展示标准位置字符串，例如 `A01`、`A03`、`B03`，不展示派生的行列文案。

## 5. 组件选择与配置体验

- [x] 5.1 确保数据源 `chart_type` 包含 `room3D` 时，screen 组件选择器展示 `3D机房`。
- [x] 5.2 数据源不包含 `room3D` 时，不展示 `3D机房`。
- [x] 5.3 配置抽屉复用现有数据源参数配置，让用户填写 `server_room_id`。
- [x] 5.4 第一版不展示 `room3D` 专属字段映射、视角、主题、自动旋转等配置项。
- [x] 5.5 在 `source_api.json` 中内置 `CMDB 3D机房布局` 数据源，初始化后可直接选择。
- [x] 5.6 增加 screen 组件通用外观配置 `appearance.frame=panel|bare`。
- [x] 5.7 新增 `room3D` 组件默认使用 `bare` 外观，存量未配置组件继续按 `panel` 渲染。
- [x] 5.8 `bare` 查看态去掉组件标题、边框、角标和背景，编辑态仍可选中、拖拽、配置和删除。
- [x] 5.9 `room3D` 在 `bare` 外观下使用透明 Three 场景，并将房间标题、重置视角按钮和图例改为悬浮显示。

## 6. 前端测试与验证

- [x] 6.1 增加 `room3D` 数据契约校验单测或轻量脚本测试。
- [x] 6.2 增加 `room3D` 空态和错误态测试。
- [x] 6.3 增加 chart type 过滤测试，验证只有支持 `room3D` 的数据源可选。
- [x] 6.3.1 增加 screen 组件外观模式脚本测试，覆盖默认外观、`room3D` 默认 `bare` 和配置回读。
- [x] 6.4 初始化内置数据源 `cmdb/get_room3d_layout`，配置 `server_room_id`，验证 screen 能渲染指定机房。
- [ ] 6.5 手动验证 hover、click 信息浮层、重置视角和组件 resize 后渲染正常。
- [ ] 6.6 手动验证取数失败或数据格式错误时只影响当前组件。
- [x] 6.7 手动验证 `room3D` 切换 `bare` 后查看态无卡片框，编辑态仍可拖拽和打开配置。
- [x] 6.8 手动验证 `room3D` 透明沉浸态无深色背景，编辑态选中后显示浮动标题和更多操作。

## 7. 质量门禁

- [x] 7.1 后端运行目标测试，至少覆盖 CMDB `room3D` 接口相关单测。
- [x] 7.2 前端运行目标测试或脚本。
- [ ] 7.3 按改动范围运行 `cd web && pnpm lint && pnpm type-check`。
- [ ] 7.4 若后端改动范围较大，运行 `cd server && make test`；若受环境限制，记录阻塞原因和已运行的目标测试。

## 8. 第二阶段数据契约：机柜设备明细

- [x] 8.1 在 `server/apps/cmdb/tests/test_room3d_layout_nats.py` 中新增测试，断言 `get_room3d_layout` 返回 `racks[].devices`，字段包含 `device_id/device_name/model_id/rack_u_start/u_size/status`。
- [x] 8.2 扩展 `server/apps/cmdb/nats/nats.py` 的 `get_room3d_layout`，复用 `rack_room.get_rack_layout` 或同等 CMDB U 位口径生成 `devices`。
- [x] 8.3 保持 `device_count` 口径为当前用户可见直接关联设备数量，缺少有效 U 位的设备不进入 `devices`，通过 `unplaced_device_count` 暴露数量。
- [x] 8.4 在 `web/scripts/ops-analysis-room3d-test.ts` 中新增契约测试，覆盖真实 `devices`、无 `devices` 不生成占位设备、设备缺 U 位直接报错。

## 9. 第二阶段前端结构拆分

- [x] 9.1 新增 `web/src/app/ops-analysis/components/widgets/room3D/room3DMeshes.ts`，集中创建房间、地砖、机柜、柜门、设备层和选中描边。
- [x] 9.2 新增 `web/src/app/ops-analysis/components/widgets/room3D/room3DScene.ts`，集中创建 Three 场景、相机、控制器、resize、渲染循环和资源释放。
- [x] 9.3 精简 `room3D/index.tsx`，仅保留 React 状态、生命周期、hover/click 浮层和组件 UI。
- [x] 9.4 保持 `room3D` 目录内模块边界清晰，不引入 GLTF/FBX、外部贴图下载或参考项目插件代码。

## 10. 第二阶段拟真机房交互

- [x] 10.1 将当前深色网格展示升级为参考图式白色地砖、长方形低墙、嵌入式主入口大门、默认视角下方近墙可见的大门、粗白结构柱、后墙左侧成组电箱/设备柜、少量后墙门窗和光照更真实的机房场景。
- [x] 10.2 将机柜升级为深灰金属柜体、柜门网格、顶部编号、内部设备层，设备层只使用 `devices` 真实 U 位，不生成占位层。
- [x] 10.3 实现机柜 hover 高亮、click 选中、选中绿色描边和信息浮层。
- [x] 10.4 实现点击已选机柜打开/关闭柜门；仅当当前视角距离过远时轻微聚焦相机目标，点击空白处保持当前柜门和选中信息。
- [x] 10.5 确保 `bare` 模式下 3D 场景仍透明融入画布，但房间自身地面和墙体正常可见。
- [x] 10.6 实现打开机柜后点击设备层抽出设备，并在右侧展示设备详情浮层。
- [x] 10.7 拉开机柜行列间距，降低开门和设备抽出时的相邻机柜遮挡。
- [x] 10.8 扩大机房地面和围合墙面范围，并将前后排间距调整为支持柜前查看设备的视角。
- [x] 10.9 增强墙面、门窗框、机柜金属纹理和 U 位刻度，避免柜体与设备过黑导致不可辨识。
- [x] 10.10 收敛设备抽出距离，并确保点击已抽出设备可弹回、点击打开机柜内部空白不关闭柜门或穿透到后排。

## 11. 第二阶段验证

- [x] 11.1 运行 CMDB `room3D` 目标后端测试。
- [x] 11.2 运行 `web/scripts/ops-analysis-room3d-test.ts`。
- [x] 11.3 对新增/拆分的 `room3D` 前端文件运行 ESLint。
- [x] 11.4 使用内置浏览器验证 185 机房可渲染、hover/click 浮层、柜门打开、重置视角和透明画布效果。
