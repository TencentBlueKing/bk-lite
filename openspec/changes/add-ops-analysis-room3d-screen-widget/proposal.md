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
