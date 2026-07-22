## ADDED Requirements

### Requirement: 统一筛选项定义

系统 SHALL 允许用户在仪表盘级别定义统一筛选项，每个筛选项包含：唯一标识(id)、参数键(key)、显示名称(name)、控件类型(type: 'string' | 'timeRange')、默认值(defaultValue)、显示顺序(order)、启用状态(enabled)。

#### Scenario: 添加关键字输入筛选项
- **WHEN** 用户在统一筛选配置弹窗中添加一个 key='namespace'、type='string' 的筛选项
- **THEN** 系统创建筛选项定义并存储到 Dashboard.filters.definitions

#### Scenario: 添加时间范围筛选项
- **WHEN** 用户在统一筛选配置弹窗中添加一个 key='time_range'、type='timeRange' 的筛选项
- **THEN** 系统创建筛选项定义并存储到 Dashboard.filters.definitions

#### Scenario: 编辑筛选项显示名称
- **WHEN** 用户修改筛选项的显示名称
- **THEN** 系统更新 Dashboard.filters.definitions 中对应筛选项的 name 字段

#### Scenario: 删除筛选项
- **WHEN** 用户删除一个筛选项
- **THEN** 系统从 Dashboard.filters.definitions 中移除该筛选项，且所有组件对该筛选项的绑定自动失效

---

### Requirement: 参数自动扫描

系统 SHALL 自动扫描画布上所有组件的数据源参数，收集 filterType='filter' 且 type 为 'string' 或 'timeRange' 的参数，按 key + type 联合去重后供用户选择。

#### Scenario: 扫描并去重参数
- **WHEN** 用户打开统一筛选配置弹窗
- **THEN** 系统扫描所有组件数据源参数，按 key + type 联合去重，显示可选参数列表，每项包含：参数 key、类型、匹配组件数、默认显示名（取自 alias_name 或 name）

#### Scenario: 过滤不支持的参数类型
- **WHEN** 组件数据源存在 filterType='filter' 但 type='number' 的参数
- **THEN** 该参数不出现在可选列表中（本期仅支持 string 和 timeRange）

#### Scenario: 过滤非筛选参数
- **WHEN** 组件数据源存在 filterType='fixed' 或 filterType='params' 的参数
- **THEN** 该参数不出现在可选列表中

---

### Requirement: 组件绑定配置

系统 SHALL 允许用户为每个组件配置与统一筛选项的绑定关系，绑定通过开关控制，仅当组件数据源参数的 key 和 type 与统一筛选项匹配时才可启用绑定。

#### Scenario: 启用匹配的绑定
- **WHEN** 组件数据源存在 key='namespace'、type='string' 的参数，且统一筛选存在相同 key + type 的筛选项
- **THEN** 用户可开启该绑定开关，系统将绑定关系存储到 LayoutItem.valueConfig.filterBindings

#### Scenario: 禁用不匹配的绑定
- **WHEN** 组件数据源存在 key='env'、type='string' 的参数，但统一筛选存在 key='env'、type='number' 的筛选项
- **THEN** 绑定开关显示为禁用状态，并提示"类型不匹配"

#### Scenario: 无匹配参数时禁用
- **WHEN** 组件数据源不存在与某统一筛选项 key 匹配的参数
- **THEN** 该筛选项的绑定开关显示为禁用状态，并提示"组件无此参数"

---

### Requirement: 筛选值联动

系统 SHALL 在统一筛选值变更时，自动触发所有已绑定组件重新请求数据，使用最新的筛选值。

#### Scenario: 关键字输入值变更
- **WHEN** 用户在筛选栏中修改关键字输入的值
- **THEN** 所有绑定到该筛选项的组件立即使用新值重新请求数据

#### Scenario: 时间范围值变更
- **WHEN** 用户在筛选栏中修改时间范围的值
- **THEN** 所有绑定到该筛选项的组件立即使用新时间范围重新请求数据

#### Scenario: 组件未绑定时不受影响
- **WHEN** 用户修改统一筛选值，但某组件未绑定到该筛选项
- **THEN** 该组件不触发重新请求

---

### Requirement: 参数合并优先级

系统 SHALL 按以下优先级合并参数：固定参数(filterType='fixed') > 统一筛选参数 > 组件私有参数(filterType='params') > 数据源默认参数。

#### Scenario: 固定参数优先
- **WHEN** 数据源定义 filterType='fixed' 的参数，且该参数 key 存在统一筛选绑定
- **THEN** 使用数据源定义的固定值，忽略统一筛选值

#### Scenario: 统一筛选优先于私有参数
- **WHEN** 组件绑定了统一筛选，且组件自身也配置了该参数的私有值
- **THEN** 使用统一筛选值，忽略组件私有配置

#### Scenario: 无统一筛选值时使用私有参数
- **WHEN** 组件绑定了统一筛选，但统一筛选值为空
- **THEN** 不传该参数（统一筛选无值时按"不传"处理）

---

### Requirement: 绑定失效检测

系统 SHALL 在每次加载仪表盘时校验所有组件的绑定有效性，失效时在组件右上角显示警告图标。

#### Scenario: 筛选项被删除导致失效
- **WHEN** 组件绑定的 filterId 在 Dashboard.filters.definitions 中不存在
- **THEN** 该绑定标记为失效，组件右上角显示警告图标，Hover 提示"筛选项已删除"

#### Scenario: 数据源参数被删除导致失效
- **WHEN** 组件绑定的 filterId 对应的 key 在组件当前数据源中不存在
- **THEN** 该绑定标记为失效，组件右上角显示警告图标，Hover 提示"参数已不存在"

#### Scenario: 参数类型变更导致失效
- **WHEN** 组件绑定的参数 key 存在，但 type 与统一筛选项不匹配
- **THEN** 该绑定标记为失效，组件右上角显示警告图标，Hover 提示"类型不匹配"

#### Scenario: 失效不阻塞组件渲染
- **WHEN** 组件存在失效绑定
- **THEN** 组件正常渲染，使用数据源默认值或私有配置，仅显示警告图标

---

### Requirement: 筛选栏显示

系统 SHALL 在仪表盘顶部显示统一筛选栏，仅当存在已启用的筛选项时显示。

#### Scenario: 筛选栏渲染
- **WHEN** Dashboard.filters.definitions 中存在 enabled=true 的筛选项
- **THEN** 仪表盘顶部显示筛选栏，按 order 字段排序渲染各筛选控件

#### Scenario: 空状态不显示
- **WHEN** Dashboard.filters.definitions 为空或所有筛选项 enabled=false
- **THEN** 筛选栏不显示

#### Scenario: 编辑态显示配置入口
- **WHEN** 仪表盘处于编辑态
- **THEN** 筛选栏显示 [设置] 按钮，点击打开配置弹窗

#### Scenario: 查看态隐藏配置入口
- **WHEN** 仪表盘处于查看态
- **THEN** 筛选栏不显示 [设置] 按钮，仅允许修改筛选值

---

### Requirement: YAML 导入导出

系统 SHALL 在 YAML 导入导出时包含 Dashboard.filters 和各组件的 filterBindings 配置。

#### Scenario: 导出包含筛选配置
- **WHEN** 用户导出仪表盘 YAML
- **THEN** 导出内容包含 filters.definitions 和各组件的 valueConfig.filterBindings

#### Scenario: 导出不含运行时值
- **WHEN** 用户导出仪表盘 YAML
- **THEN** filters.values 为空对象（运行时值不持久化到导出文件）

#### Scenario: 导入恢复筛选配置
- **WHEN** 用户导入包含 filters 配置的 YAML
- **THEN** Dashboard.filters.definitions 和各组件 filterBindings 正确恢复
