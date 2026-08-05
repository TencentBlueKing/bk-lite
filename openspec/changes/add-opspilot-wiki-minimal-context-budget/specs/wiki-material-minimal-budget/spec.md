## ADDED Requirements

### Requirement: 系统必须提供两个单文件构建环境变量

系统 MUST 集中读取 `WIKI_BUILD_MAX_LLM_CALLS_PER_MATERIAL` 和 `WIKI_BUILD_MAX_TOTAL_TOKENS_PER_MATERIAL`，默认值分别为 64 和 60,000。调用次数 MUST 是硬安全熔断；累计 token MUST 是软审计阈值。缺失时使用默认值；存在但不是正整数时阻止服务启动。

#### Scenario: 构建变量缺失
- **WHEN** 服务启动且两个构建变量未配置
- **THEN** 每个文件 MUST 使用 64 次调用硬熔断和 60,000 token 软阈值

#### Scenario: 构建变量非法
- **WHEN** 任一构建变量为 0、负数、非整数或无法解析
- **THEN** 服务 MUST 拒绝启动
- **AND** 错误 MUST 指明非法环境变量名称

### Requirement: 批量上传必须按文件独立计量

每个文件 MUST 具有独立 BuildRecord、调用次数、累计 token、checkpoint 和结果状态。批量上传 MUST NOT 在文件之间共享计数。

#### Scenario: 一个文件触发硬熔断
- **WHEN** 文件 A 触发系统安全熔断而文件 B 仍可正常处理
- **THEN** A MUST 保存独立失败状态和 checkpoint
- **AND** B MUST 继续独立构建

### Requirement: 长文件必须按单次安全上下文自适应处理

资料解析 MUST 确定性执行，不得因累计 LLM token 软阈值失败。能够在单次安全输入窗口内处理的文件 MUST 直接生成最终页面。超出时 MUST 按安全输入大小完整 Map，不得用固定分块数量把单次 Prompt 扩大到模型窗口之外。Map 输出超出最终生成窗口时 MUST 分层 Reduce。

#### Scenario: 解析文本需要五个以上 Map
- **WHEN** 完整解析文本按安全输入窗口需要五个以上 Map
- **THEN** 系统 MUST 继续处理全部分块
- **AND** MUST NOT 返回“超过四次 Map 上限”

#### Scenario: Map 输出不能一次 Reduce
- **WHEN** Map 输出总量超过最终页面生成的安全输入窗口
- **THEN** 系统 MUST 分组压缩后继续归并
- **AND** 每轮 MUST 缩小条目数或估算 token

### Requirement: 构建累计 token 必须作为软阈值审计

系统 MUST 累计页面生成、Map、Reduce、冲突比较和语义 Overview 的输入输出 token。确定性解析、Index、目录、数据库和图谱操作 MUST 不计入 LLM token。累计 token 超过配置值 MUST 继续必要构建并在 trace 标记软阈值已超过。

#### Scenario: 必要 Reduce 将超过 60,000 token
- **WHEN** 下一次必要 Reduce 预计使累计 token 超过 60,000
- **THEN** 系统 MUST 继续执行 Reduce
- **AND** BuildRecord MUST 记录 `soft_budget_exceeded=true`
- **AND** MUST NOT 仅因该软阈值把资料标记为构建失败

#### Scenario: 软阈值耗尽后的可选 Overview
- **WHEN** 最终页面已经形成且累计 token 达到软阈值
- **THEN** 系统 MAY 跳过 LLM 语义 Overview
- **AND** MUST 保留确定性 Overview

### Requirement: 系统硬安全保护不得激活不完整 Generation

调用次数、单次上下文、归并轮次和归并无进展 MUST 作为硬安全保护。触发时系统 MUST 保存 checkpoint，将 BuildRecord 标记为 `budget_exhausted`，并拒绝激活不完整 Generation。

#### Scenario: 调用次数熔断
- **WHEN** 一个文件的下一次调用将超过配置的调用次数
- **THEN** 系统 MUST 停止并保存已完成 Map/Reduce checkpoint
- **AND** 当前 active Generation MUST 保持不变

#### Scenario: 归并没有进展
- **WHEN** 一轮 Reduce 没有降低条目数或估算 token
- **THEN** 系统 MUST 以稳定错误码停止异常循环
- **AND** MUST NOT 无限追加 LLM 调用

### Requirement: 冲突比较必须保持紧凑且不随旧知识线性增长

疑似冲突 MUST 先使用 Generation Index 召回有限候选，再最多执行一次批量正文证据比较。累计 token 软阈值 MUST NOT 让必要冲突比较直接失败；证据仍须受单次安全上下文限制。

#### Scenario: 旧知识很多
- **WHEN** 新资料只与少数旧页面相关
- **THEN** 系统 MUST 只加载有限候选真实正文
- **AND** MUST 最多执行一次批量冲突比较

### Requirement: 预算决策必须可审计

BuildRecord MUST 保存配置值快照、每阶段调用次数、输入/输出实际或估算 token、软阈值状态、硬拒绝点、checkpoint 指纹和最终状态。

#### Scenario: 管理员查看长文件构建
- **WHEN** 文件累计 token 超过软阈值但构建成功
- **THEN** 管理员 MUST 能看到已用调用数、token 和软阈值状态
- **AND** 最终状态 MUST 是成功而不是 budget_exhausted

### Requirement: Web 必须在高用量输入前提示管理员

单个文件严格大于 500 MiB 时，Web MUST 在上传请求前要求管理员确认。新增 URL 资料时，Web MUST 提示当前页面正文和图片较多可能增加耗时与模型用量。确认或提示 MUST NOT 形成后端文件大小/token 拒绝规则。

#### Scenario: 管理员确认大文件
- **WHEN** 管理员选择一个大于 500 MiB 的文件并确认继续
- **THEN** Web MUST 正常提交上传
- **AND** 后端 MUST 正常解析和构建

#### Scenario: 管理员取消大文件
- **WHEN** 管理员在确认框取消
- **THEN** Web MUST NOT 发起上传请求