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
