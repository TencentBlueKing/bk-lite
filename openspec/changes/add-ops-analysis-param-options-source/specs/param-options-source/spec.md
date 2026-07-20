# Capability: param-input-source

## Purpose

为运营分析参数提供统一输入配置能力。参数可声明为输入框、下拉选择或单选按钮；下拉与单选可使用静态选项或动态数据源选项。内置数据源可通过 `sourceRef/rest_api` 声明默认选项来源，组件配置与统一筛选使用一致的编辑器内部交互。

## ADDED Requirements

### Requirement: 统一参数输入配置模型

系统 SHALL 使用 `InputControlConfig` 表达参数输入方式，支持 `input`、`select`、`radio` 三种控件类型；当控件类型为 `select` 或 `radio` 时，系统 SHALL 支持静态选项和动态数据源选项两类来源。

#### Scenario: 普通输入框配置
- **WHEN** 参数配置为 `{ control: "input" }`
- **THEN** 系统按参数原始类型渲染输入控件，不读取选项来源

#### Scenario: 静态下拉配置
- **WHEN** 参数配置为 `control: "select"` 且 `optionsSource.type: "static"`
- **THEN** 系统使用 `staticItems` 渲染下拉选项

#### Scenario: 静态单选配置
- **WHEN** 参数配置为 `control: "radio"` 且 `optionsSource.type: "static"`
- **THEN** 系统使用 `staticItems` 渲染单选按钮

#### Scenario: 动态选项配置
- **WHEN** 参数配置为 `control: "select"` 或 `control: "radio"` 且 `optionsSource.type: "dynamic"`
- **THEN** 系统从配置的数据源拉取选项并映射为 `{ label, value }`

---

### Requirement: sourceRef/rest_api 内置来源声明

系统 SHALL 支持内置数据源参数通过 `sourceRef: { type: "rest_api", value: string }` 声明动态选项来源。运行时系统 SHALL 根据 `rest_api` 查找真实数据源 ID，再调用该数据源获取选项。

#### Scenario: 通过 rest_api 解析动态来源
- **WHEN** `inputConfig.optionsSource.sourceRef` 为 `{ type: "rest_api", value: "cmdb/get_room_list" }`
- **THEN** 系统从数据源列表中查找 `rest_api === "cmdb/get_room_list"` 的数据源
- **AND** 使用查到的数据源 ID 拉取选项数据

#### Scenario: sourceRef 找不到数据源
- **WHEN** 系统无法找到 `sourceRef.value` 对应的数据源
- **THEN** 参数控件回退为原始输入控件
- **AND** 参数配置入口仍可打开

#### Scenario: 用户手动配置保存 sourceId
- **WHEN** 用户在编辑器中选择某个数据源作为动态选项来源
- **THEN** 系统保存 `sourceId`
- **AND** 不生成 `sourceRef`

---

### Requirement: 统一编辑器

系统 SHALL 提供共享编辑器 `paramInputConfigEditor.tsx`，组件配置抽屉和统一筛选配置都使用该编辑器。编辑器 SHALL 先选择控件类型，再在下拉选择或单选按钮时选择选项来源。

#### Scenario: 选择控件类型
- **WHEN** 用户打开 `ParamInputConfigEditor`
- **THEN** 编辑器显示“输入框 / 下拉选择 / 单选按钮”三种控件类型

#### Scenario: 输入框不显示选项来源
- **WHEN** 用户选择“输入框”
- **THEN** 编辑器不显示选项来源配置

#### Scenario: 下拉或单选显示选项来源
- **WHEN** 用户选择“下拉选择”或“单选按钮”
- **THEN** 编辑器显示“自定义选项 / 数据源选项”两种选项来源

#### Scenario: 自定义选项
- **WHEN** 用户选择“自定义选项”
- **THEN** 编辑器允许用户维护 `{ label, value }` 列表

#### Scenario: 数据源选项
- **WHEN** 用户选择“数据源选项”
- **THEN** 编辑器允许用户选择数据源，并选择 value 字段和 label 字段

#### Scenario: 保存输入框配置
- **WHEN** 用户选择“输入框”并保存
- **THEN** 系统写入 `{ control: "input" }`

---

### Requirement: 数据源管理参数表不提供输入配置入口

系统 SHALL 不在数据源管理参数表中提供参数输入配置编辑入口。数据源管理参数表 SHALL 只维护参数名、类型、默认值、过滤类型等基础字段。

#### Scenario: 参数表无选项列
- **WHEN** 用户打开数据源管理参数表
- **THEN** 表格不显示本变更新增的“选项”列或参数输入配置按钮

#### Scenario: 数据源定义仍可携带 inputConfig
- **WHEN** 数据源来自 `source_api.json` 且参数包含 `inputConfig`
- **THEN** 系统保存并返回该字段
- **AND** 数据源管理参数表不提供手动编辑该字段的 UI

---

### Requirement: 组件配置抽屉消费与覆盖 inputConfig

系统 SHALL 在组件配置抽屉中消费数据源参数定义自带的 `inputConfig`，并允许 widget 级覆盖写入 `ViewConfigItem.valueConfig.dataSourceParams[i].inputConfig`。

#### Scenario: 继承数据源定义 inputConfig
- **WHEN** widget 参数没有自己的 `inputConfig`
- **AND** 数据源参数定义存在 `inputConfig`
- **THEN** 组件配置抽屉使用数据源参数定义的输入配置渲染控件

#### Scenario: widget 级覆盖
- **WHEN** 用户在组件配置抽屉中打开参数配置并保存
- **THEN** 系统写入 `widget.valueConfig.dataSourceParams[i].inputConfig`
- **AND** 后续渲染优先使用 widget 级配置

#### Scenario: 覆盖为普通输入框
- **WHEN** 用户在组件配置抽屉中选择“输入框”并保存
- **THEN** 该 widget 参数后续渲染为普通输入控件

#### Scenario: 不提供恢复默认按钮
- **WHEN** 用户已经保存 widget 级覆盖
- **THEN** 编辑器不显示“恢复默认”按钮

---

### Requirement: 统一筛选使用同一编辑器与运行逻辑

系统 SHALL 让统一筛选配置使用 `paramInputConfigEditor.tsx`。统一筛选运行态 SHALL 通过同一套输入配置归一化与渲染逻辑处理 select 与 radio。

#### Scenario: 统一筛选编辑输入框
- **WHEN** 用户在统一筛选中选择“输入框”并保存
- **THEN** 筛选项保存 `inputConfig: { control: "input" }`

#### Scenario: 统一筛选编辑下拉
- **WHEN** 用户在统一筛选中选择“下拉选择”并配置选项来源
- **THEN** 筛选项保存对应 `inputConfig`
- **AND** 运行态渲染 Select

#### Scenario: 统一筛选编辑单选
- **WHEN** 用户在统一筛选中选择“单选按钮”并配置选项来源
- **THEN** 筛选项保存对应 `inputConfig`
- **AND** 运行态渲染 Radio.Group

#### Scenario: select 和 radio 都支持动态来源
- **WHEN** 统一筛选项的控件类型为 `select` 或 `radio`
- **AND** 选项来源为动态数据源
- **THEN** 两者都通过同一套动态选项解析逻辑获取选项

---

### Requirement: 动态选项失败回退原始输入

系统 SHALL 将动态选项来源视为输入增强。若来源不可用、请求失败、无数据或映射后无可展示选项，系统 SHALL 回退到该参数原始输入控件，而不是禁用参数配置。

#### Scenario: 动态来源请求失败
- **WHEN** 动态选项来源请求返回错误
- **THEN** 参数控件回退原始输入控件
- **AND** 用户仍可输入参数值

#### Scenario: 动态来源无选项
- **WHEN** 动态来源返回空数组或映射后无可展示项
- **THEN** 参数控件回退原始输入控件

#### Scenario: 配置入口仍可用
- **WHEN** 动态来源失败导致控件回退输入框
- **THEN** 参数配置 icon 仍然可用

---

### Requirement: 旧 options 读取兼容

系统 SHALL 对旧 `options: Array<{ label, value }>` 做读取兼容。若实体没有 `inputConfig` 但存在旧 `options`，系统 SHALL 将其视为静态下拉配置。新写入配置 SHALL 只写 `inputConfig`。

#### Scenario: 读取旧 options
- **WHEN** 系统读取到旧 `options` 且没有 `inputConfig`
- **THEN** 系统归一化为 `control: "select"` 且 `optionsSource.type: "static"`

#### Scenario: 新配置写入
- **WHEN** 用户通过新编辑器保存配置
- **THEN** 系统只写入 `inputConfig`
- **AND** 不写入新的 `optionsConfig`

---

### Requirement: 内置选项源：CMDB 机房列表

系统 SHALL 注册 `CMDB 机房列表` 内置数据源，并让 `CMDB 3D机房布局.server_room_id` 默认通过 `sourceRef/rest_api` 使用该数据源作为下拉选项来源。

#### Scenario: 数据源列表中可见
- **WHEN** 用户打开“运营分析 → 数据源管理”数据源列表
- **THEN** 列表中能看到 `CMDB 机房列表`
- **AND** 其 `rest_api` 为 `cmdb/get_room_list`
- **AND** 其 `chart_type` 为空数组

#### Scenario: 机房 ID 默认下拉
- **WHEN** 用户在组件配置抽屉中选择 `CMDB 3D机房布局`
- **THEN** `server_room_id` 参数默认渲染为下拉选择
- **AND** 下拉选项来自 `cmdb/get_room_list`

#### Scenario: 数据源返回 CMDB 原始字段
- **WHEN** 后端 `cmdb/get_room_list` 被调用
- **THEN** 返回 `items: [{ _id: 1, inst_name: "机房A", model_id: "server_room", ... }]`
- **AND** 不重命名为 `id` 或 `name`

#### Scenario: 按当前用户权限过滤
- **WHEN** 当前用户没有某机房查看权限
- **THEN** 该机房不出现在 `cmdb/get_room_list` 返回列表中

#### Scenario: 复用 CMDB 现成权限过滤
- **WHEN** 服务层列出机房
- **THEN** 通过 `InstanceManage.instance_list(model_id="server_room", permission_map=...)` 复用权限过滤

---

### Requirement: 国际化

系统 SHALL 为统一参数输入配置编辑器、控件类型、选项来源、动态来源错误提示等 UI 元素提供中英文 i18n 文案。

#### Scenario: 切换语言文案同步
- **WHEN** 用户切换系统语言
- **THEN** 参数输入配置相关文案全部同步切换
