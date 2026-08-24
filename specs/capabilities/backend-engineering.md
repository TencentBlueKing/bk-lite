# 后端编码规范 / 高频陷阱清单

> 后端开发的预防性规范:写代码时照此避坑。每条给 **✅ 正确姿势** 与 **❌ 反模式**。
> 与 [工程质量](engineering-quality.md)、`server/docs/testing-guide.md`、[平台安全](platform-security.md)和[平台可靠性](platform-reliability.md)配套。
> 用法:改 `server/` 或 `agents/` 代码前,对照与你改动相关的小节。

## 1. 鉴权与多租户(最高频 —— 务必先看)

- ✅ **每个 DRF view/action 显式权限校验**,`@HasPermission(...)` 绝不注释掉;mixin 默认权限要确认覆盖到每个 action。
  - ❌ 权限装饰器被注释/缺失,任意已登录用户即可执行敏感操作或枚举全量。
- ✅ **每个 NATS handler 校验调用方与 org**,不信任消息体里的 `group_id`/`pusher`/身份字段。
  - ❌ 信任客户端传入的身份字段 → 内网任意节点跨组织读写。
- ✅ **`skip_permission` 不得硬编码旁路**;采集/内部调用也要带真实 caller。
- ✅ **权限过滤 fail-closed**:权限数据为空 → 返回 `none()`,绝不 fail-open 返回全量。
- ✅ **`@api_exempt` 仅限真正公开端点**;任何写操作禁用。
- ✅ **按对象读取校验归属(防 IDOR)**:`get_object` 限定在调用者租户/团队内。
- ✅ **跨团队操作校验 team 归属**:重跑/批量操作前确认对象属于调用者。

## 2. 查询与性能

- ✅ **列表/批量接口强制分页上界**,拒绝 `page_size=-1` 或无界拉取。
  - ❌ 无上界查询/循环 → 可被远程触发 OOM/DoS。
- ✅ **不把整表加载进内存做过滤/唯一性/统计**,用 DB 层 `filter`/`exists`/`annotate`/`count`。
- ✅ **FK/M2M 用 `select_related`/`prefetch_related` 防 N+1**。
- ✅ **多次 `count()`/独立查询合并为单次 `annotate`**;热路径禁冗余 `count()`/`exists()` 调试查询。
- ✅ **高频过滤字段加 `db_index`**;重查询结果加缓存(带失效)。

## 3. 事务与一致性

- ✅ **多表/多步写包 `transaction.atomic()`**,部分失败整体回滚。
- ✅ **通知/外部副作用放 `transaction.on_commit`**,不在落库成功前推送。
  - ❌ 先发通知后落库 → 失败时通知与数据不一致。
- ✅ **read-modify-write 用 `select_for_update` 或 `F()` 原子更新**,防并发竞态。
- ✅ **进程级缓存必须有失效机制**,配置变更后能刷新。

## 4. 输入边界与错误响应

- ✅ **不裸 `int(request.GET.get(...))` / 不裸字典取键**,用 serializer 校验,或 `try` + 返回 **400**。
  - ❌ 裸转换/裸取键 → 非法输入触发 500,或崩溃 worker。
- ✅ **鉴权/授权失败返回 403**,不是 500;错误响应结构统一。
- ✅ **不吞异常**:`except` 要么处理要么上抛 + 记日志;禁空/裸 `except` 返回脏数据。
- ✅ **NATS handler 入参做类型/存在校验**,非法输入不得崩 worker。

## 5. 序列化与契约

- ✅ **禁止 `fields = "__all__"`**,显式列字段,新增字段不会意外外泄。
- ✅ **敏感字段(secret/password/token)`write_only=True`**,绝不随 GET 响应返回。
- ✅ **JSONField 入库前做结构校验**,不静默存任意值。

## 6. 密钥与下发(交叉,详见 SECURITY / RELIABILITY)

- ✅ **密钥不明文返回 / 不进日志**;解密失败跳过或告警,绝不回退返回密文。
- ✅ **下发链路校验 TLS / host key**,禁 `skip-tls` / `AutoAddPolicy` / `StrictHostKeyChecking=no`。
- ✅ **下发不伤宿主**:资源边界、幂等可回滚、不可逆操作预检 —— 见 [可靠性红线 §2.5](platform-reliability.md)。

## 7. 数据库可移植与图库

- ✅ **禁原生 SQL**:走 Django ORM(`DB_ENGINE` 多方言,raw SQL 跨库易碎);确需复杂查询用 ORM 表达式。
- ✅ **图库(CMDB)用参数化查询**,禁拼接 Cypher / 禁 Neo4j 语法(本项目用 FalkorDB)。

## 8. 日志契约

### 8.1 logger 来源

- ✅ **`server/apps/<app>/` 内统一从 `apps.core.logger` 引入本 app 的 logger，并别名为 `logger`**:
  ```python
  from apps.core.logger import {app_name}_logger as logger
  ```
  现有导出见 `server/apps/core/logger.py`（如 `cmdb_logger`、`opspilot_logger`、`alert_logger`、`monitor_logger`、`node_logger`、`job_logger`、`mlops_logger`、`log_logger`、`system_mgmt_logger`、`console_mgmt_logger`、`operation_analysis_logger`、`nats_logger`、`celery_logger`）。`core` / 跨 app 共享工具可用默认 `from apps.core.logger import logger`。
  - ❌ `from loguru import logger`、直接 `logging.getLogger(...)`、或引入其他 app 的 `*_logger`。
  - ❌ 新增 app logger 时绕过 `apps/core/logger.py` 就地创建。

### 8.2 模板、等级与失败所有权

- ✅ **稳定模板 + 惰性参数**：stdlib logging 使用 `logger.info("event=task_completed task_id=%s", task_id)`；独立算法服务沿用 loguru 的 `{}` 参数风格。禁止用 f-string、字符串拼接、`%` 或 `.format()` 预先把动态值固化进模板。
- ✅ **等级表达运行语义**：INFO 只记录可独立检索的 accepted、lifecycle、terminal 或有界批次汇总；逐项成功、循环进度、函数开始/结束和内部 read/decode/retry 阶段使用 DEBUG 或删除；可恢复降级、跳过和业务失败使用 WARNING；真正需要运维处理的失败才使用 ERROR。
- ✅ **一个失败只有一个 traceback 所有者**：由最接近业务语义且拥有 task/run/execution/callback ID 的边界在 `except` 中持有真实 traceback；通常使用 `logger.exception`。异常正文可能含 payload、响应或凭据时，必须改用原始 `error.__traceback__` + 脱敏替代异常正文的 `exc_info` / Loguru `opt(exception=...)`，同时记录稳定 `error_type`；Loguru 生产 handler 必须显式 `diagnose=False`，禁止从 traceback 帧展开 locals。仅记录字符串 call-chain 不能替代 traceback。下层继续上抛时不得重复 ERROR，也不得手工调用 `traceback.format_exc()`。上层可记录不带重复堆栈的有界终态汇总。
- ✅ **失败字段可关联**：失败日志至少包含稳定 event、可用的业务关联 ID、`failed_stage` 和 `error_type`；异步链路分别表达执行结果、持久化结果与投递/ACK 结果，不用单一 `success` 掩盖部分失败。

### 8.3 安全、容量与业务兼容

- ✅ **敏感正文直接省略**：密码、token、cookie、Authorization、credential、私钥、完整 payload/result/响应正文、模板正文和未脱敏 SQL 不进入日志；不得把凭据截短后宣称安全。确需关联时使用非凭据 ID 或项目已有的专用 sanitizer。
- ✅ **动态字段有界且单行**：用户或外部系统可控的 ID、路径、URL、subject 等只记录排障必需部分，按领域上限截断日志副本并转义 CR/LF；不得为日志修改传给业务、协议或持久化层的原值。
- ✅ **常驻运行路径不使用 `print`**：Server、Agent 和在线 serving 统一走 logger；明确面向人的 CLI、管理命令、代码生成/诊断脚本和测试工具可以使用 stdout/stderr。
- ✅ **日志改动不夹带业务契约变化**：默认保持返回值、用户可见文案、异常类型/身份、重试、状态、数据库写入、NATS subject/payload/ACK 和外部 SDK 调用不变；确需改变时必须拆分说明并补兼容与回滚测试。

### 8.4 日志测试契约

- ✅ **测试日志行为而非文案镜像**：稳定模板改动需断言模板与独立参数，并用 `LogRecord.getMessage()` 或等价 formatter 验证最终渲染；异常链需断言语义边界恰好一条 traceback ERROR、保留真实 traceback 对象且关联字段完整；异常正文安全时可用原异常，可能敏感时必须使用受控代理异常且不修改原异常。
- ✅ **安全断言覆盖完整输出**：使用唯一哨兵值验证 message、参数和带 traceback 的完整格式化结果均不包含凭据、payload、响应正文或其他禁记内容；脱敏异常代理还必须证明 `exc_info` / Loguru exception tuple 保留原始 traceback 对象和调用帧、替代正文受控且不修改原异常。Loguru 测试必须直接使用生产 handler，并断言 `diagnose=False`，不得另加测试专用安全 sink 绕过生产配置。只断言 mock 调用或“截断后看不到完整值”不算通过。
- ✅ **回归同时锁定业务契约**：日志测试必须同步证明原返回值、用户可见错误、异常类型与对象身份、状态/持久化及协议字段保持不变；不得只验证 mock logger 被调用。

## 9. 架构卫生

- ✅ **控制文件/类规模**:发现 God 文件(>500 LOC)/God 类及时拆分;重复逻辑(3+ 处)抽公共 helper,避免漂移漏改。

## 10. 高风险通用能力(跨模块)

- ✅ **安全边界变更按迁移处理**:新增或收紧鉴权、校验、加密、超时等边界前,必须盘点存量调用方、存量数据和默认行为,并明确兼容策略、迁移步骤与回滚方案。
  - ❌ 只证明新逻辑更安全,未验证存量契约与回滚路径就直接上线。
- ✅ **异步任务使用可验证的状态机与 fencing**:任务领取、执行、超时回收、重试和结果回写必须基于明确状态转换及执行令牌;旧执行被回收后不得覆盖新执行结果,重复执行必须幂等。
  - ❌ 仅靠 RUNNING 标记或进程存活判断任务所有权,导致超时旧执行与新执行并发写入。
- ✅ **持久化与外部副作用形成一致性闭环**:消息派发、通知、任务投递、文件操作等必须在持久化成功后执行,并具备幂等键、失败补偿和可重试语义。
  - ❌ 外部动作与本地状态各自成功或失败,留下无法确认真实结果的半完成状态。
- ✅ **敏感数据保护覆盖完整生命周期**:存储加密、版本标识、密钥轮换、存量迁移、掩码编辑、异常链、日志、指标、备份和回滚路径均不得泄露明文凭据。
  - ❌ 只保护 API 响应,却让凭据进入异常上下文、连接串、日志、指标或历史备份。
- ✅ **关键路径测试覆盖不变量与失败路径**:涉及权限、并发、事务、异步任务或外部系统时,除正常路径外必须验证越权失败、重复执行、并发竞争、部分失败、超时、回滚及旧版本兼容性。
  - ❌ 只验证一次正常请求成功,未证明失败和重试后系统仍保持一致。
- ✅ **并发授权与状态变更在锁内重读判定依据**:进入事务或取得锁后重新读取所有参与判定的关联对象,用条件更新、版本号或 fencing 提交;不得复用锁前加载的 ORM 对象或关系缓存。
  - ❌ 锁住主对象却继续使用锁前的团队、权限或状态快照,形成 TOCTOU 并覆盖并发变更。
- ✅ **变化数据的批量遍历使用稳定 keyset 游标**:回填、迁移或清理可能并发增删改的数据时,按不可变且唯一的键推进游标,保存断点并保证重复执行幂等。
  - ❌ 使用 offset 或非唯一排序遍历变化数据,导致跨页遗漏、重复处理或覆盖错误对象。
- ✅ **异步回调绑定可信执行身份**:回调必须校验 caller、访问范围、run/attempt 标识及执行令牌;重复、乱序和过期回调不得覆盖当前终态。
  - ❌ 以“先到先得”或仅凭业务 ID 接受回调,让伪造或旧执行结果固化为最终状态。

---

## 提交前快速自检(后端)

改 `server/` / `agents/` 时逐条对照:
- [ ] view/handler 有显式鉴权,fail-closed,不信任客户端身份字段
- [ ] 列表有分页上界,无全量内存过滤,FK 有 select_related/prefetch
- [ ] 多步写有 `atomic`,通知在 `on_commit`,RMW 原子
- [ ] 输入经校验,异常不吞,失败码语义正确(400/403 非 500)
- [ ] serializer 无 `__all__`,敏感字段 write_only
- [ ] 日志符合 §8：来源正确、模板稳定、等级真实、失败单一持有 traceback，关联字段完整且动态值安全有界
- [ ] 无原生 SQL,图查询参数化
- [ ] 安全边界变更已盘点存量契约,有迁移与回滚方案
- [ ] 异步状态有 fencing/幂等,持久化与外部副作用可补偿重试
- [ ] 并发判定在锁内重读,批量遍历使用稳定游标,回调绑定执行身份
- [ ] 敏感数据在存储、异常、日志、指标、备份和回滚链路均不泄露
- [ ] 新增行为有测试,关键路径覆盖失败/并发/回滚/兼容场景,覆盖率达标(见 [工程质量 §4](engineering-quality.md))
