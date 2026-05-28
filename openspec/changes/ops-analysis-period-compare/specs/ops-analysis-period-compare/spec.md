## ADDED Requirements

### Requirement: 共享 compare 配置

系统 SHALL 通过共享 `ValueConfig` 为运营分析单值类配置声明是否开启“相对上个周期变化”，并允许仪表盘组件和拓扑单值节点复用同一 compare 配置语义。

#### Scenario: 仪表盘单值卡开启 compare
- **WHEN** 用户为仪表盘单值卡开启 compare 开关
- **THEN** 系统保存该组件的 compare 配置为开启状态

#### Scenario: 拓扑单值节点开启 compare
- **WHEN** 用户为拓扑单值节点开启 compare 开关
- **THEN** 系统保存该节点的 compare 配置为开启状态

#### Scenario: 无有效时间参数时不可开启 compare
- **WHEN** 单值类配置不存在可识别的有效时间范围参数
- **THEN** 系统不应允许该配置启用 compare

---

### Requirement: 共享 compare 查询层

系统 SHALL 通过一层共享的前端 compare 查询能力处理 compare 取数，避免仪表盘和拓扑分别实现基线时间计算和双请求逻辑。

#### Scenario: 仪表盘与拓扑复用同一 compare 查询层
- **WHEN** 仪表盘单值卡和拓扑单值节点都开启 compare
- **THEN** 两者都通过同一共享 compare 查询层获取 compare 数据

#### Scenario: compare 查询层输出统一结果模型
- **WHEN** compare 查询完成
- **THEN** 共享 compare 查询层至少向消费端输出 `currentData` 和 `baselineData`

---

### Requirement: compare 复用原始单周期接口

系统 SHALL 参考日志分析页做法，通过两次同构单周期请求完成 compare，而不是要求后端或 NATS 接口原生支持 compare 协议。

#### Scenario: compare 不修改后端接口协议
- **WHEN** 组件开启 compare
- **THEN** 系统继续调用现有单周期数据源接口
- **AND** 不要求后端接口新增 compare 请求参数

#### Scenario: compare 双请求除时间外参数一致
- **WHEN** 共享 compare 查询层构造当前周期请求和基线周期请求
- **THEN** 两次请求除时间范围外的所有参数必须保持一致

---

### Requirement: compare 基线周期时间规则

系统 SHALL 将基线周期定义为与当前时间范围等长、紧邻当前周期之前的时间窗，并与日志分析页现有规则保持一致。

#### Scenario: 相对时间范围基线计算
- **WHEN** 当前时间范围为最近 15 分钟
- **THEN** 基线周期为其之前连续的 15 分钟时间窗

#### Scenario: 绝对时间范围基线计算
- **WHEN** 当前时间范围为用户选择的绝对起止时间
- **THEN** 基线周期应通过当前时间窗长度回推得到

---

### Requirement: 前端消费端负责 compare 展示计算

系统 SHALL 由前端消费端基于 `currentData` 和 `baselineData` 计算 compare 展示结果，不要求数据源接口预先返回差值、变化率或方向。

#### Scenario: 仪表盘单值卡计算较上一周期结果
- **WHEN** 仪表盘单值卡已配置 `selectedFields[0]`
- **THEN** 前端应从 `currentData` 和 `baselineData` 中按相同字段路径取值并计算变化结果

#### Scenario: 拓扑单值节点复用同一 compare 数据模型
- **WHEN** 拓扑单值节点需要展示 compare 结果
- **THEN** 前端应基于共享 compare 查询层输出的 `currentData` 和 `baselineData` 完成节点展示逻辑
