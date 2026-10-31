## ADDED Requirements

### Requirement: 公共工作负载路由
系统 SHALL 在公共 Celery 配置中定义 critical、notification、state、background 四个逻辑队列，按完整任务名路由已核实任务。默认 celery 队列 SHALL 由后台池消费；未映射且已注册的任务 SHALL 可执行并产生限频诊断。路由 SHALL 不激活未启用任务、不改变任务函数与参数。

#### Scenario: 节点与告警采用不同执行池
- **WHEN** 已核实的节点收敛任务和告警扫描任务通过正常异步入口发布
- **THEN** 两者分别投递 state 和 critical，节点任务不能被告警池消费

#### Scenario: 未映射任务兜底
- **WHEN** 已注册任务没有公共路由且发布者未显式指定路由
- **THEN** 消息进入 celery 并由后台池消费，同时记录未映射诊断，不丢弃消息

### Requirement: 统一独立执行池
系统 SHALL 对原默认工作负载使用一套四 worker 拓扑，分别消费 critical、notification、state、background+celery，每个 worker 使用 prefork 和独立节点名，显式声明队列；上游既有 OpsPilot、报表渲染和补丁维护专用消费者 SHALL 保留，不合并到四池。每池 SHALL 通过 MIN/MAX 配置保底与峰值执行子进程数，不按机器内存提供不同部署档位。部署 SHALL 保持唯一 Beat。

#### Scenario: 状态池和后台池饱和
- **WHEN** state 和 background 执行槽位被测试任务占满，告警池有可用槽位
- **THEN** critical 任务能够在告警池启动，不等待其他两池释放槽位

#### Scenario: 通知任务阻塞
- **WHEN** notification 槽位被占用且 critical 有可用槽位
- **THEN** critical 任务仍可开始执行

### Requirement: 有界原生弹性
系统 SHALL 使用 Celery 5.4 支持的 prefork autoscale，命令范围顺序为 MAX,MIN，并校验 1≤MIN≤MAX。系统 SHALL 根据原生 autoscaler 的池内需求在范围内伸缩，配置收缩等待参数，只回收可退出的空闲子进程，不为缩容终止运行任务。系统 SHALL 不把 threads 作为已支持原生伸缩的池，不把原生 autoscale 描述为全局队列 SLO 或实时内存控制器。

#### Scenario: 负载增加与回落
- **WHEN** 真实 broker 的测试任务使 worker 需求超过 MIN，随后任务完成且满足收缩条件
- **THEN** 子进程数在 MIN 到 MAX 范围内增长并回落，不中断繁忙任务；实际范围和伸缩事件可观察

#### Scenario: 固定容量配置
- **WHEN** 某池设置 MIN=MAX
- **THEN** 该池保持固定执行容量，仍使用相同配置解析和预算校验

### Requirement: 最大容量预算校验
系统 SHALL 使用唯一解析器生成运行配置。各池 MIN/MAX 和部署总并发上限 SHALL 显式配置，不能把并发 1 作为已验证容量推荐。所有可同时运行实例的 MAX 之和 SHALL 不超过总预算，副本数和升级重叠 SHALL 纳入部署核对。系统 SHALL 拒绝缺失参数、非法范围、遗漏/重复消费者和旧并发变量歧义，避免旧 worker 同时自启动。关闭 Celery 的既有部署行为 SHALL 保持有效。

#### Scenario: 最小容量合规但最大容量超限
- **WHEN** MIN 之和小于总预算但所有实例的 MAX 之和超过预算
- **THEN** 发布检查失败，不允许依靠独立 autoscaler 在运行时竞争无约束额度

#### Scenario: 旧并发变量产生歧义
- **WHEN** 旧 CELERY_CONCURRENCY 仍影响新运行配置
- **THEN** 启动前报出迁移错误，不把旧值复制成每个 worker 的并发

### Requirement: 保留上游执行策略
系统 SHALL 保留最新上游 prefork 的有效任务软/硬超时、子进程按任务数/内存回收、ACK 和重试行为，不引入忽略这些配置的兼容层。四池预取乘数 SHALL 为1，禁止无限值0；它不代表ETA及全部驻留消息的硬上限。

#### Scenario: 任务达到声明超时
- **WHEN** 任务达到上游声明的软/硬超时
- **THEN** 原生prefork按既有契约处理，不因队列隔离取消超时

#### Scenario: 子进程达到回收阈值
- **WHEN** 子进程完成任务且达到已配置任务数或RSS回收阈值
- **THEN** 原生prefork回收并补充子进程，后续任务继续执行

### Requirement: 有效路由覆盖检查
发布检查 SHALL 核对线上注册任务、实际生产者、启用的数据库周期任务及显式 queue/exchange/routing_key 覆盖。检查 SHALL 报告未注册任务、未分类任务和偏离目标的最终目的地。需调整数据库路由时 SHALL 仅使用 ORM 更新已审查的路由字段，并提供 dry-run、快照和恢复能力。

#### Scenario: 周期任务覆盖公共路由
- **WHEN** PeriodicTask 显式路由与批准的队列不一致
- **THEN** 发布检查报告冲突并阻止宣称隔离已完成；修正不改变其任务名、启停、周期或参数

#### Scenario: 线上任务不在本地清单
- **WHEN** 生产注册或发布证据包含本地未确认的任务
- **THEN** 先取得实际实现和最终路由证据再批准分类，不用名称猜测填充路由

### Requirement: 业务语义保持
架构改造 SHALL 保持现有任务函数、调度频率、参数、业务状态机、数据库模型、远端操作、ACK 与重试语义。系统 SHALL 不通过清空队列、消息过期、队列截断或自动清锁达到隔离目标。

#### Scenario: 仅更新运行架构
- **WHEN** 部署路由、worker 或公共观测变更
- **THEN** 相同业务输入继续使用原任务实现，业务去重、关联算法、补算与通知流程没有因本变更被修改
