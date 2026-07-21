# Tasks: add-ops-analysis-param-options-source

## 1. 类型与工具函数

- [x] 1.1 在 `web/src/app/ops-analysis/types/dataSource.ts` 定义 `InputControlConfig`、静态选项来源、动态选项来源和 `SourceRef` 类型
- [x] 1.2 在 `ParamItem` 中新增 `inputConfig?: InputControlConfig`
- [x] 1.3 保留旧 `options` 字段读取兼容，不再新增/使用 `optionsConfig` 作为新主模型
- [x] 1.4 在 `web/src/app/ops-analysis/types/dashBoard.ts` 为 `UnifiedFilterDefinition` 新增 `inputConfig?: InputControlConfig`
- [x] 1.5 编写 `web/src/app/ops-analysis/utils/paramInputConfigUtils.ts`
  - `normalizeInputConfig(entity)`
  - `resolveDynamicSourceId(...)`
  - `mapDynamicItems(...)`
- [x] 1.6 工具函数测试覆盖：已有 `inputConfig`、旧 `options`、空配置、`sourceId`、`sourceRef/rest_api`、动态数据映射

## 2. 统一编辑器 paramInputConfigEditor

- [x] 2.1 新增/替换 `web/src/app/ops-analysis/components/paramInputConfigEditor.tsx`
- [x] 2.2 文件名使用小写开头，React 组件导出为 `ParamInputConfigEditor`
- [x] 2.3 编辑器第一段实现控件类型：输入框 / 下拉选择 / 单选按钮
- [x] 2.4 当控件类型为输入框时，不展示选项来源配置
- [x] 2.5 当控件类型为下拉选择或单选按钮时，展示选项来源：自定义选项 / 数据源选项
- [x] 2.6 自定义选项支持维护 `{ label, value }` 列表
- [x] 2.7 数据源选项支持选择数据源、拉取字段、选择 valueField 和 labelField
- [x] 2.8 用户手动选择数据源时保存 `sourceId`，不生成 `sourceRef`
- [x] 2.9 不提供“恢复内置默认”按钮
- [x] 2.10 Modal body 长内容使用 antd v5 `styles.body` 控制滚动，保证底部按钮可见
- [x] 2.11 添加/调整 zh 和 en i18n key

## 3. 运行渲染组件 paramInputControl

- [x] 3.1 新增/替换 `web/src/app/ops-analysis/components/paramInputControl.tsx`
- [x] 3.2 `control: "input"` 渲染原始参数类型对应输入控件
- [x] 3.3 `control: "select"` 解析选项并渲染 Select
- [x] 3.4 `control: "radio"` 解析选项并渲染 Radio.Group
- [x] 3.5 动态来源有 `sourceId` 时直接调用 `getSourceDataByApiId(sourceId, {})`
- [x] 3.6 动态来源有 `sourceRef/rest_api` 时先按 rest_api 解析真实数据源 ID，再调用 `getSourceDataByApiId`
- [x] 3.7 动态来源找不到、请求失败、无数据或映射后无可展示选项时，回退原始输入控件
- [x] 3.8 配置入口不因动态来源失败而消失

## 4. 数据源管理参数表收敛

- [x] 4.1 删除 `paramTable.tsx` 中本分支新增的“选项”列
- [x] 4.2 删除 `paramTable.tsx` 中的参数选项编辑 state、handler、Modal 调用
- [x] 4.3 确认数据源管理参数表不写入 `inputConfig`
- [x] 4.4 保持参数名、类型、默认值、过滤类型等原有能力不变

## 5. 组件配置抽屉接入

- [x] 5.1 在 `paramsConfig.tsx` 使用 `normalizeInputConfig` 读取参数输入配置
- [x] 5.2 读取优先级：widget 级 `dataSourceParams[i].inputConfig` 优先，其次数据源定义 `params[i].inputConfig`
- [x] 5.3 有 `inputConfig` 时使用 `paramInputControl.tsx` 渲染
- [x] 5.4 每行保留配置 icon，点击打开 `ParamInputConfigEditor`
- [x] 5.5 保存编辑器结果到 `widget.valueConfig.dataSourceParams[i].inputConfig`
- [x] 5.6 选择“输入框”并保存后，后续该 widget 参数使用普通输入控件
- [x] 5.7 不提供“恢复内置默认”交互

## 6. 统一筛选接入

- [x] 6.1 `unifiedFilterConfigModal.tsx` 使用 `ParamInputConfigEditor`
- [x] 6.2 新配置写入 `UnifiedFilterDefinition.inputConfig`
- [x] 6.3 删除/替换旧 `FilterOptionsModal` 调用
- [x] 6.4 `unifiedFilterBar.tsx` 通过 `normalizeInputConfig` 渲染 input/select/radio
- [x] 6.5 select 和 radio 都支持静态与动态来源
- [x] 6.6 修复 radio 只读取旧 `options` 的问题
- [x] 6.7 旧 `inputMode + options` 仅做读取兼容

## 7. CMDB 机房列表内置来源

- [x] 7.1 在 `server/apps/cmdb/services/rack_room.py` 保留/新增 `list_server_rooms(permission_map, user_info) -> list`
  - 复用 `InstanceManage.instance_list(model_id="server_room", ...)`
  - `page_size=1000`
  - `order="inst_name"`
  - 返回 CMDB 原始字段，不做 `_id` / `inst_name` 重命名
- [x] 7.2 在 `server/apps/cmdb/nats/nats.py` 保留/新增 `get_room_list(user_info=None, **kwargs)`
  - 复用 `_build_nats_permission_map(user_info)`
  - 返回 `{"items": [...]}`
- [x] 7.3 补充/调整后端测试，覆盖返回结构、权限过滤参数透传、空列表
- [x] 7.4 在 `source_api.json` 注册 `CMDB 机房列表`
- [x] 7.5 在 `CMDB 3D机房布局.server_room_id` 上声明 `inputConfig`
  - `control: "select"`
  - `optionsSource.type: "dynamic"`
  - `sourceRef: { type: "rest_api", value: "cmdb/get_room_list" }`
  - `valueField: "_id"`
  - `labelField: "inst_name"`

## 8. 清理旧实现命名

- [x] 8.1 删除或重命名 `paramOptionsEditor.tsx`
- [x] 8.2 删除或重命名 `paramOptionsSourceSelect.tsx`
- [x] 8.3 删除或重命名 `paramOptionsUtils.ts`
- [x] 8.4 将 i18n 命名从 `paramOptions.*` 收敛为参数输入配置语义
- [x] 8.5 清理不再需要的 `optionsConfig` 类型、变量名和注释

## 9. 验证

- [x] 9.1 执行 `NEXTAPI_INSTALL_APP=ops-analysis pnpm exec tsx <工具测试脚本>` 验证输入配置工具函数
- [x] 9.2 执行 `NEXTAPI_INSTALL_APP=ops-analysis pnpm type-check`
- [x] 9.3 执行相关 CMDB 后端单测
- [ ] 9.4 手动验证：`CMDB 3D机房布局.server_room_id` 默认显示当前用户可见机房下拉
- [ ] 9.5 手动验证：动态来源失败时回退普通输入，参数仍可配置
- [ ] 9.6 手动验证：组件配置和统一筛选编辑器内部交互一致
- [ ] 9.7 手动验证：统一筛选 select/radio 都能使用静态和动态来源
- [x] 9.8 执行 `git diff --check`
