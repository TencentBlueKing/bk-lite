# 日志可诊断性第六轮统一治理

关联 Issue：#4963

## 目标

在不改变业务返回、异常传播、协议和持久化语义的前提下，处理已确认的剩余日志噪声、错误 logger 来源、装饰性运行日志、生产 `print` 绕过和低风险敏感片段。

## 共同契约

1. 日志调整默认不改变返回值、异常类型、重试、状态、数据库写入、NATS subject/payload/ACK 和云 SDK 请求。
2. 一个失败由最接近业务语义且能提供关联 ID 的边界持有真实 traceback；下层继续传播时不重复 ERROR。异常正文可能含 payload、响应或凭据时，保留原始 traceback 对象并用受控异常正文替代原正文；Loguru 生产 handler 显式禁用 locals 诊断（`diagnose=False`），字符串帧摘要不能单独替代 traceback。
3. INFO 只表达可独立检索的生命周期、终态或有界汇总，不表达函数内 Loading/Read/Decode 等阶段，也不使用 emoji/分隔线装饰。
4. DEBUG 可记录有界诊断摘要；不记录 payload、响应正文、凭据、token、cookie、模板正文或未脱敏 SQL。
5. `server/apps/<app>` 从 `apps.core.logger` 使用对应 app logger；共享 Core 使用默认 logger。`apps/core/logger.py` 自身和按异常模块动态选择 logger 的兼容封装除外。
6. `print` 只允许明确面向人的 CLI、管理命令、代码生成/诊断脚本和测试工具；常驻 Server/Agent 运行路径必须走统一 logger。

## 模块契约

### S3JSONField

- `to_python(path)` 和 descriptor 读取的返回、缓存、gzip/raw 兼容及失败返回保持不变；
- 一次成功读取不产生 INFO，只产生一个 `s3_json_load_succeeded` DEBUG；
- DEBUG 只包含最长 500 字符的对象路径、是否压缩、存储/解码字节数、值类型和条目数；
- 空对象、坏 JSON、storage 异常继续产生 WARNING/ERROR。

### logger 来源

- 活跃 `server/apps` 生产文件不再就地 `logging.getLogger`；
- 迁移只改变 logger 路由入口，不改变日志级别、模板、参数和控制流；
- app 与 logger 映射以 `apps/core/logger.py` 的现有导出为准。

### print 与装饰日志

- NATS listener 不输出完整消息数据，只记录稳定 handler/subject 元数据；
- Server/Stargazer 常驻运行路径的异常与阶段信息进入统一 logger；
- 云插件不把完整云响应写 stdout；
- 离线训练 CLI、显式诊断脚本和管理命令的人类可读 stdout 不纳入生产 logger 迁移。

### 敏感片段

- 微信 token 交换失败只记录稳定事件、HTTP/业务状态和错误类型，不记录完整响应；
- 补丁执行过期结果保留 task/target/stage 关联，不记录 fencing token；
- 已经经过 `_mask_*` / `_sanitize_*` 的 NATS 连接错误保持现有诊断信息。

### 规范沉淀

- `specs/capabilities/backend-engineering.md` 长期记录 logger 来源、稳定模板、日志等级、异常所有权、关联字段、安全容量和业务兼容契约；
- `AGENTS.md` 提供 Agent 执行短清单并指向长期契约，后续修改日志不依赖历史 change spec 才能发现规则。

## 测试契约

- 每类运行时修复至少一个可回退失败的行为测试；
- logger 来源以导入/日志路由测试或静态精确断言覆盖，不只比较候选总数；
- 敏感日志用哨兵值证明完整 formatter 输出不包含原值；脱敏异常代理同时证明原始 traceback 对象与调用帧保留、替代正文受控且原异常/业务传播不变；Loguru 直接验证生产 handler 均为 `diagnose=False`；
- 长期规范与 Agent 短清单覆盖本轮共同契约，且不存在相互矛盾的等级、安全或 stdout 规则；
- 最终按模块运行相关回归，并执行全仓重扫记录新基线和剩余候选。

## 排除范围

- 不机械修复全部 L001/P1 历史候选；
- 不改变云 SDK、NATS、数据库或外部 API 契约；
- 不将 stdout 禁令扩展到明确 CLI/诊断工具。
