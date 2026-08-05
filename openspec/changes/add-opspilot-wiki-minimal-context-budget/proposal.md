## Why

Wiki 问答需要可预测的硬上限，但资料构建不能因为普通的累计 token 阈值而拒绝管理员已确认上传的资料。现阶段不需要复杂 Budget Profile；系统应以少量环境变量限制问答，并用单文件调用熔断、单次上下文和异常归并保护构建，同时完整记录构建用量。

## What Changes

- 保留 3 个问答环境变量：最大 LLM 调用次数、最大 Wiki 知识上下文 token、最大回答输出 token，继续作为硬上限。
- 保留 2 个单文件构建环境变量：最大 LLM 调用次数是异常循环硬熔断；累计输入输出 token 是软审计阈值。
- 未配置时使用内置默认值；已配置非法值时服务启动失败。
- Wiki 只负责 Index/Overview/页面/图谱/来源摘要预算；Bot/ChatFlow 继续负责系统提示、当前问题、历史和最终模型窗口。
- 每个上传文件独立计数、checkpoint、失败和重试；批量上传不共享额度。
- 普通文件在单次安全上下文内直接生成页面；长文件按安全输入窗口自适应 Map，Map 输出过大时分层 Reduce，再生成最终页面。
- 超过 60,000 token 只记录软阈值告警，不中断构建；只有调用次数、单次上下文或异常归并等系统安全保护才拒绝激活不完整 Generation。
- 文件大于 500 MB 时上传前提示并要求管理员确认；URL 新增页提示正文和图片较多可能增加耗时与模型用量。确认后仍正常解析和构建。
- 本变更不增加 Profile、数据库预算配置、审批、用户调额或向量预算。

## Capabilities

### New Capabilities

- `wiki-query-minimal-budget`: 定义问答环境变量、知识 token 口径、调用次数、输出限制和 Bot/ChatFlow 边界。
- `wiki-material-minimal-budget`: 定义单文件调用硬熔断、累计 token 软阈值、自适应长文件处理、checkpoint 和上传提示。

### Modified Capabilities

- 无。

## Impact

- 配置：保留 5 个系统环境变量及严格启动校验。
- 后端：集中读取预算、估算和累计 usage；构建 trace 区分软阈值与硬安全拒绝。
- 问答：知识上下文和 LLM 调用继续具有硬上限。
- 构建：每个文件独立预算，自适应 Map/分层 Reduce，BuildRecord 记录软阈值和硬停止原因。
- Web：显示大文件和 URL 用量提醒，不提供用户调额入口。