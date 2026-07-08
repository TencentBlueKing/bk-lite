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
