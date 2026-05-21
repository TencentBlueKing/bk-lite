## ADDED Requirements

### Requirement: 工具调用卡片垂直布局
系统 SHALL 将工具调用展示从横排布局改为垂直单行卡片布局，每个工具占据完整的一行宽度。

#### Scenario: 多个工具调用垂直排列
- **WHEN** 对话中存在多个工具调用
- **THEN** 每个工具卡片独占一行，从上到下垂直排列

### Requirement: 工具卡片默认折叠
系统 SHALL 默认以折叠状态展示工具卡片，仅显示工具名称和状态图标。

#### Scenario: 工具调用完成后的默认展示
- **WHEN** 工具调用完成并渲染到对话区域
- **THEN** 卡片显示为折叠状态，仅展示：工具图标、工具名称、状态图标（✓ 或 loading）、展开箭头（▶）

### Requirement: 工具卡片可展开
系统 SHALL 支持点击卡片展开，显示 Input 和 Output 详情区域。

#### Scenario: 点击折叠状态的卡片
- **WHEN** 用户点击处于折叠状态的工具卡片
- **THEN** 卡片展开，显示 Input 和 Output 区域，箭头变为向下（▼）

#### Scenario: 点击展开状态的卡片
- **WHEN** 用户点击处于展开状态的工具卡片
- **THEN** 卡片折叠，隐藏 Input 和 Output 区域，箭头变为向右（▶）

### Requirement: Input 区域展示
系统 SHALL 在展开状态下显示 Input 区域，包含 Command 和 Input Params 两部分。

#### Scenario: 展示工具输入信息
- **WHEN** 工具卡片处于展开状态
- **THEN** Input 区域显示：
  - Command 标签下显示 `$ {工具名称}`
  - Input Params 标签下显示格式化的 JSON 参数（args）

### Requirement: Output 区域展示
系统 SHALL 在展开状态下显示 Output 区域，展示工具执行结果。

#### Scenario: 展示工具输出结果
- **WHEN** 工具卡片处于展开状态且工具已完成执行
- **THEN** Output 区域显示工具的执行结果（result）

#### Scenario: 工具执行中无输出
- **WHEN** 工具卡片处于展开状态但工具仍在执行中
- **THEN** Output 区域显示加载状态或为空

### Requirement: 长内容处理
系统 SHALL 对过长的 Input/Output 内容进行合理的展示限制。

#### Scenario: JSON 参数过长
- **WHEN** Input Params 的 JSON 内容超过显示区域
- **THEN** 内容区域可滚动查看，不影响整体布局

#### Scenario: 输出结果过长
- **WHEN** Output 内容超过显示区域
- **THEN** 内容区域可滚动查看，不影响整体布局
