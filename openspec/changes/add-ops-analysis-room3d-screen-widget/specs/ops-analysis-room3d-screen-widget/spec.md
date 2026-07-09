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
