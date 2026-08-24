# 日志可诊断性第六轮：清理剩余运行时噪声

## 背景

前五轮已经处理完整凭据、采集循环 INFO、Server Core 简单动态模板，以及 Server/Stargazer 异步失败所有权。最新 master 全量重扫仍有 6,463 个静态候选：P0 4、P1 1,846、P2 4,481、P3 132。这些数字包含误报、CLI 输出和历史兼容代码，不能机械清零，但当前仍有一批可确认、可由自动测试约束的生产问题：

- S3 JSON 字段一次正常读取输出 4～5 条阶段性 INFO；
- `server/apps` 中仍有模块绕过统一 app logger，就地调用 `logging.getLogger`；
- 运行时路径仍有 `print` 绕过日志系统，个别位置会打印完整消息或云接口响应；
- 部分常驻服务日志包含装饰符、分隔线和逐请求成功文案，难以稳定聚合；
- 微信失败响应和补丁执行 fencing token 被直接写入日志。

## 本轮目标

本轮作为统一治理轮，在一个 Issue/PR 内处理以下五类工作：

1. **日志噪声**：正常 S3 读取不再输出逐阶段 INFO，改为一个 DEBUG 终态摘要；保留失败 WARNING/ERROR。
2. **logger 来源**：将 `server/apps` 的活跃生产代码统一迁移到 `apps.core.logger` 对应 app logger；保留 `apps/core/logger.py` 本身和确需动态 logger 的异常封装。
3. **装饰性日志**：清理常驻服务路径中的 emoji、分隔线和无稳定事件的逐请求成功日志；不改面向人的离线训练 CLI 输出。
4. **print 绕过**：生产运行时不再用 `print` 输出消息体、云响应或异常；显式命令行工具、生成脚本和测试脚本继续使用 stdout/stderr。
5. **低风险敏感片段**：微信 token 交换失败不记录完整响应；补丁执行过期结果不记录 fencing token；已经过专用 sanitizer 的 NATS 错误不按机械候选误删。

同时把稳定模板、日志等级、异常所有权、关联字段、安全容量和生产 stdout 边界沉淀到长期工程规范，并在 `AGENTS.md` 提供执行短清单。

## 复现场景

### S3 读取噪声

通过 Django 字段公开读取接口读取一条未压缩 JSON 对象。实际返回正确数据，但产生 Loading、Read、Not gzipped、Successfully loaded 等多条 INFO。预期返回值不变，INFO 为 0，仅保留一个有界 DEBUG 摘要。

### print 绕过

让 NATS listener 收到带 payload 的消息或让云插件请求失败。实际内容直接进入 stdout，无法按 logger、级别、event 和关联 ID 治理。预期生产路径统一走 logger，且不记录完整 payload/响应。

## 影响范围

- Server Core、实际命中的业务 app 与 NATS listener；
- Stargazer 活跃运行时与少量云插件边界；
- 算法在线 serving 的装饰性运行日志。

这是跨模块工程治理，风险档为中，人工决策闸为 `automated_deep_review`：不改 API/NATS schema、数据库、任务状态、返回值或异常传播；按模块分别测试，并执行三轨审查。PR 以一个干净提交交付，避免把本地诊断工具或中间治理历史带入远端。

## 明确排除

- 不批量修改 3,684 个 L001 或 1,846 个 P1 机械候选；
- 不把 CLI、管理命令、诊断脚本、测试脚本的必要 stdout 一律改成 logger；
- 不删除失败 ERROR、traceback、重试终态或 Run 汇总；
- 不修改云 SDK 请求参数、响应解析、重试和资源操作；
- 不以截断 token 作为安全方案：不可记录的值直接省略，需关联时使用非凭据 ID。

## 验收条件

- [ ] S3 正常读取返回值不变、零 INFO、一个 DEBUG 终态；失败日志与缓存语义保持；
- [ ] 本轮覆盖的 `server/apps` 文件不再就地创建 logger，日志路由到正确 app；
- [ ] 本轮覆盖的生产 `print` 和装饰性运行日志消失，CLI stdout 保持；
- [ ] 微信响应、补丁 fencing token、payload 和云原始响应不进入日志；
- [ ] 长期工程规范与 `AGENTS.md` 已覆盖本轮共同日志契约；
- [ ] 各模块行为测试先红后绿，相关回归、全量重扫和三轨审查通过。

## 回滚

无数据迁移和协议变化，可通过 `git revert` 整体回滚。
