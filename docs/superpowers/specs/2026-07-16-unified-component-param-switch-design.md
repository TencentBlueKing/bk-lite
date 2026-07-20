# 运营分析组件内切换统一设计

## 背景

运营分析当前存在两套相互重叠的参数交互模型：

- 普通查询参数使用 `filterType: 'params'`，字符串参数可在组件级配置输入框、下拉选择或单选按钮，并支持静态、动态选项来源。
- TopN 组件内切换使用独立的 `filterType: 'widget'`、`RuntimeParamControl` 和侧边栏“组件内切换”区块。

两套模型重复保存参数绑定、选项和运行时输入行为。新的参数输入配置已经能够表达控件类型和选项来源，因此本设计将 TopN 组件内切换合并到普通字符串参数配置中，并完整删除旧模型。

## 目标

- 使用 `filterType: 'params'`、`type: 'string'` 的参数配置组件内切换。
- 在 `ParamInputConfigEditor` 中完成输入方式、选项来源和组件内切换配置。
- 第一阶段只允许 TopN 使用组件内切换，但数据结构不与 TopN 类型绑定。
- 每个组件暂时只能启用一个组件内切换参数。
- 复用现有静态、动态选项来源和参数请求链路。
- 删除 `filterType: 'widget'`、`RuntimeParamControl` 和 TopN 专用配置区块。
- 不引入数据库迁移或长期兼容层；现有唯一数据源和组件由用户手动转换。

## 非目标

- 第一阶段不支持 TopN 以外的图表类型展示组件内切换。
- 不支持一个组件同时展示多个组件内切换控件。
- 不允许文本输入框作为组件内切换控件。
- 不改变统一筛选编辑器的行为。
- 不在组件内切换后自动保存新的参数值到组件配置。

## 数据模型

在 `InputControlConfig` 的选项型分支增加 `componentSwitch?: boolean`：

```ts
export type InputControlConfig =
  | {
      control: 'input';
    }
  | {
      control: 'select' | 'radio';
      optionsSource: StaticOptionsSource | DynamicOptionsSource;
      componentSwitch?: boolean;
    };
```

约束如下：

1. 只有 `filterType: 'params'`、`type: 'string'` 的参数可配置组件内切换。
2. `componentSwitch` 只允许出现在 `select` 或 `radio` 分支。
3. 每个组件的最终 `dataSourceParams` 中最多存在一个 `componentSwitch: true`。
4. 第一阶段只有 TopN 消费该字段。
5. 静态和动态选项继续保存在 `optionsSource`，不复制成另一份运行时配置。

删除以下旧结构：

- `DataSourceParamFilterType` 中的 `'widget'`
- `RuntimeParamValue`
- `RuntimeParamOption`
- `RuntimeParamControl`
- `ValueConfig.runtimeParamControl`
- 表单临时字段 `runtimeParamControlEnabled`

## 组件配置交互

### 编辑入口

组件侧边栏继续在查询参数区域展示 `params` 和 `fixed` 参数。字符串参数保留输入配置入口，配置作为组件级覆盖写入 `valueConfig.dataSourceParams`，不修改数据源定义。

### ParamInputConfigEditor

组件配置场景打开编辑器时：

- 控件类型为“输入框”时，不显示“组件内切换”。
- 控件类型为“下拉选择”或“单选按钮”时，在选项来源配置之前显示“组件内切换”开关。
- 当前图表不是 TopN 时，不显示开关。
- 当前组件已有另一个参数启用组件内切换时，开关保持关闭并禁用。
- 禁用提示为：`每个组件暂时只能配置一个组件内切换参数，当前已由「{参数显示名}」启用。`
- 编辑当前已启用的参数时，允许关闭开关。
- 从 `select` 或 `radio` 改成 `input` 时，清除 `componentSwitch`。

编辑器需要由组件配置调用方传入当前图表类型和已占用参数信息。统一筛选配置调用同一编辑器时不传组件切换能力，因此不显示该开关。

### 图表类型切换

组件从 TopN 切换到其他图表类型时：

- 自动删除组件参数覆盖中的 `componentSwitch`。
- 保留 `control` 和完整 `optionsSource`。
- 以后切回 TopN 时，用户可以重新开启组件内切换。

这样可以避免非 TopN 组件持有界面不可见、当前也不生效的隐藏开关配置。

### 保存校验

界面禁用不是唯一保障。组件提交前必须再次统计 `componentSwitch: true` 的参数：

- 0 个或 1 个时允许保存。
- 超过 1 个时阻止保存，并明确列出冲突参数。
- `input` 分支上异常存在的 `componentSwitch` 按未启用处理并在规范化时清除。

### 选项变化后的参数值校正

下拉选择或单选按钮的选项发生变化后，组件当前参数值必须与有效选项保持一致：

- 当前值仍在有效选项中时保留当前值。
- 当前值不在有效选项中且选项非空时，静默重置为 `options[0].value`，不展示提示消息。
- 选项为空、动态选项加载失败或尚未解析完成时，保留当前值，不擅自清空或覆盖。

静态选项在用户确认输入配置时立即执行校正。动态选项在成功加载后执行校正；组件保存前对已经成功解析出选项的参数再做一次兜底校验。普通下拉、单选参数与组件内切换参数复用同一套规则，不能只修正标题区运行时值。

值匹配必须同时比较类型和值，例如字符串 `"1"` 与数字 `1` 视为不同值。

## 运行时行为

### 解析有效配置

运行时从数据源参数与组件级 `dataSourceParams` 合并出最终参数配置，然后寻找唯一满足以下条件的参数：

- `filterType === 'params'`
- `type === 'string'`
- `inputConfig.control` 为 `select` 或 `radio`
- `inputConfig.componentSwitch === true`

非 TopN 图表不解析或展示组件内切换。

### 选项加载

- 静态来源直接使用 `staticItems`。
- 动态来源复用现有数据源请求、`valueField`、`labelField` 和选项映射逻辑。
- 动态选项加载失败、配置无效或结果为空时，不展示标题区控件；组件仍使用已保存参数值查询，不让整个组件进入错误状态。

### 初始值

初始值取组件保存的参数值。若该值不在有效选项中，则使用第一项，并且首次组件数据请求也使用同一个回退值，保证控件状态与请求参数一致。

该运行时回退与配置阶段的参数值校正复用同一个纯函数，避免配置表单、保存结果和组件请求采用不同判断规则。

旧 `RuntimeParamControl.defaultValue` 不再保留；现有唯一组件在手动转换时，将期望的默认选项写入组件参数值。

### 标题区展示

- `control: 'select'` 渲染下拉框。
- `control: 'radio'` 在组件配置区仍使用单选按钮，在 TopN 标题区渲染 `Segmented`。

标题区控件继续复用现有 header slot 布局。控件切换后只更新当前组件实例的运行时参数值，将该值合并进数据请求参数和请求缓存签名，触发重新查询；不自动持久化组件配置。

## 旧能力删除

实现需完整删除：

- 数据源参数用途中的“组件内交互”选项及文案。
- TopN 设置区中的独立“组件内切换”区块。
- `RuntimeParamControlEditor`。
- `runtimeParamControl` 的校验、初始值、请求参数和渲染工具。
- Dashboard、Screen、Topology 对旧字段的复制和透传。
- 旧 `RuntimeParamSegmented`；新的标题区控件直接基于 `InputControlConfig` 渲染。
- 旧 Storybook 示例、测试夹具和本功能专用旧文案。

内置数据源 `server/apps/operation_analysis/support-files/source_api.json` 中的 `group_by` 参数从 `filterType: 'widget'` 改为 `filterType: 'params'`，防止新环境或初始化流程重新生成旧类型。

## 存量数据处理

不编写数据库迁移，也不保留旧配置读取兼容层。原因是当前只有一个数据源和一个 TopN 组件使用旧能力，人工转换更明确，且可避免一次性迁移与长期兼容代码形成技术债。

上线后按以下步骤处理：

1. 记录旧 TopN 配置的绑定参数、选项和值。
2. 在数据源设置页把对应参数从“组件内交互”改为“参数”，保持字符串类型并保存。
3. 打开原 TopN 组件，在查询参数区域进入该参数的输入配置。
4. 选择下拉选择或单选按钮，重新配置静态或动态选项来源。
5. 开启“组件内切换”。
6. 将组件参数值设置为期望的首次选中值并保存组件。
7. 验证标题区控件、初始查询、切换查询和重新打开后的配置。

重新保存唯一组件后，新配置不再输出 `runtimeParamControl`，旧字段随组件保存被清除。

## 异常与降级

- 多个参数同时启用：阻止组件保存并展示冲突参数。
- 动态选项请求失败或为空：隐藏标题区控件，继续用已保存参数查询。
- 初始值不在选项中：回退第一项，并使用回退值发起首次请求。
- 配置阶段已成功解析出非空选项但当前值失效：静默重置为第一项，不展示提示消息。
- 切换数据源：移除不属于新数据源的组件参数覆盖，不能把旧开关绑定到同名但无关的参数。
- 切换离开 TopN：清除 `componentSwitch`，保留其他输入配置。
- 异常的 `input + componentSwitch`：按未启用处理并清除异常字段。

## 测试策略

### 类型与纯函数

- 组件内切换候选参数筛选。
- 单参数唯一性校验及冲突参数报告。
- 静态、动态选项解析。
- 已保存初始值与第一项回退。
- 选项值按“类型 + 值”匹配，字符串 `"1"` 不匹配数字 `1`。
- 运行时参数合并和请求签名变化。
- 非 TopN 不启用组件内切换。

### 配置界面

- TopN 的 `select/radio` 显示开关，`input` 不显示。
- 非 TopN 不显示开关。
- 统一筛选编辑器不显示开关。
- 已有其他占用参数时禁用开关并显示参数名。
- 编辑当前占用参数时可以关闭。
- 离开 TopN 清除开关但保留控件和选项来源。
- 多参数异常状态在保存阶段被拒绝。
- 静态选项变更后，失效参数值立即静默重置为第一项。
- 动态选项成功加载后，失效参数值静默重置为第一项。
- 选项为空或动态加载失败时保留原参数值。

### 保存与恢复

- `componentSwitch` 随组件级 `dataSourceParams` 保存并恢复。
- 数据源原始参数不被组件级配置修改。
- 保存前对已解析选项执行兜底校正，不再持久化已失效的参数值。
- 保存结果不再包含 `runtimeParamControl` 或临时启用字段。
- Dashboard、Screen、Topology 的正常参数配置不因删除旧透传字段而丢失。

### 运行时

- `select` 在标题区渲染下拉框。
- `radio` 在标题区渲染 `Segmented`。
- 切换选项触发带新参数值的数据请求。
- 运行时值参与请求缓存签名。
- 动态选项失败、空数据及无效初始值按设计降级。

### 清理检查

生产代码、内置数据和当前测试夹具中不再出现：

- `filterType: 'widget'`
- `runtimeParamControl`
- `runtimeParamControlEnabled`
- `RuntimeParamControl`

历史设计文档和历史实施计划作为决策记录保留，不纳入生产代码清理要求。

## 验收标准

1. TopN 组件的字符串查询参数可以在输入配置弹窗中开启组件内切换。
2. 每个组件最多开启一个，其他参数开关禁用并显示占用参数。
3. 下拉选择在标题区显示下拉框，单选按钮在标题区显示 `Segmented`。
4. 静态和动态选项来源均可工作。
5. 初始值来自组件参数，无效时回退第一项且首次请求一致。
6. 切换触发重新查询但不自动保存组件配置。
7. 非 TopN 和统一筛选编辑器不显示组件内切换开关。
8. 离开 TopN 自动清除开关但保留输入控件配置。
9. 旧 widget 类型、旧侧栏和旧运行时配置从生产代码中完全删除。
10. 用户按手动步骤转换唯一存量数据源和组件后，功能连续且数据库不再保留该组件的旧字段。

## 恢复后的最终实现补充

- 当组件标题区没有可用的 header slot 时，TopN 通过 `WidgetRenderer` 接收同一个切换控件并在内容区顶部内联回退显示；有 header slot 时只通过 portal 渲染，不重复内联。
- 动态选项通过 `sourceRef` 定位数据源时，数据源列表这一阶段完成后立即检查 generation。请求已 stale 时直接返回 `null`，不再启动第二阶段数据请求。
- 运行时 active value 必须按“类型 + 值”存在于完整 options 中，才允许写入额外请求参数；preview 的前 5 条永不参与该判断。
- 删除旧 `runtimeParamControl.ts` 后，其中与参数切换无关的 TopN `loading/error/empty/ready` 状态能力迁入 `topNContentState.ts`，保持原渲染和 `onReady` 语义。
