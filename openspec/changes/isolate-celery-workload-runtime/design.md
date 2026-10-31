# Celery 工作负载隔离与有界弹性设计

## 基线与范围

基于 TencentBlueKing/bk-lite master `7fc417be88`（2026-10-30 刷新）。用户确认仅做架构改造，使用通用配置、不分机器档位。整机16–32GB包含所有组件，不推断并发1够用。

旧 `dd39ab8c23` 调研包含88项定义，已被[当前182项清单](../../../docs/celery-current-task-inventory.md)替代。新基线已有 prefork、按任务数/内存回收、OpsPilot/报表/补丁维护专用消费者；这些是现状，不能为套用旧计划移除。

## 执行拓扑

默认队列工作负载分为四个独立 worker：

| Worker | 队列 | 职责 |
|---|---|---|
| critical | critical | 监控/日志/APM/RUM 检测与告警生命周期 |
| notification | notification | 通知、outbox 交付与补偿，隔离慢外部 I/O |
| state | state | 节点/作业/采集/导入导出状态收敛与补偿 |
| background | background、celery | CMDB 关联、导入导出、采集、批处理；承接未知及历史消息 |

既有 OpsPilot 四队列、dashboard_report_render、patch_maintenance 保留原专用 worker、原并发变量和原任务显式 queue，不合并进四池。完整安装有7个 Celery worker 主进程（原来4个），非“每个模块/每个队列新建 worker”。队列名本身不是内存成本主因，进程及依赖副本才是。

准确名称清单182项：critical12、notification22、state20、background94、既有专用34。清单支持装饰器显式 name 和模块级常量，不能从源码函数路径直接猜注册名；每个显式 queue 都有测试验证保留。静态定义不代表实际已安装注册，严格运行检查仍须核对生产者、Beat 和远端 worker 注册。

## 弹性、回收与内存预算

保留 Celery5.4 原生 prefork。四池使用 `--autoscale=MAX,MIN`、`--prefetch-multiplier=1` 和唯一节点名前缀；不混用旧 CELERY_CONCURRENCY。收缩等待 AUTOSCALE_KEEPALIVE 默认60秒。MIN≥1、MIN≤MAX；每池数值必须显式配置。

保留上游 CELERY_MAX_TASKS_PER_CHILD（默认200）与 CELERY_MAX_MEMORY_PER_CHILD（默认512000 KiB）以及任务自身软/硬超时、ACK、重试声明。没有自定义执行池或 threads 兼容层。回收发生在子进程完成任务之后，内存阈值不是单任务实时硬内存上限。

所有同时运行同构副本的容量预算：

`CELERY_TOTAL_CONCURRENCY_LIMIT ≥ replicas × (四池 MAX 总和 + DASHBOARD_REPORT_RENDER_CONCURRENCY + 1个补丁维护槽 + 已启用 OpsPilot 的 OPSPILOT_CELERY_CONCURRENCY)`

报表和补丁 worker 在当前 release 固定安装，必须计入；INSTALL_APPS为空或包含opspilot时再计入其并发。部署升级新旧实例重叠也必须占预算。多副本显式声明唯一 Beat 归属。该校验是进程并发预算，不是内存控制器：API/NATS/数据库/图库/算法服务、子进程RSS、COW破坏及任务内部并发均需现场测量。不给未经测量的生产 MIN/MAX 推荐。

## 启动与配置

Django 和启动器共用 .env 加载器，以当前工作目录向上查找，已导出环境变量优先。release 保留 migrate失败立即停止、batch_init及专用进程条件清理流程；batch_init完成后用纯本地配置解析生成默认四池及Beat配置，替代旧默认worker和独立beat.conf。生成器不注册业务任务，不访问DB/broker，不等待运行期进程。错误容量配置属于资源边界错误，禁止启动不受控消费者，给出具体变量修复提示；外部可选资源的失败策略保持上游。

新默认worker仍加载共享Django应用，不通过伪造精简注册来节省内存；后续若考虑裁剪，必须另行验证信号、模型与任务依赖。

## 路由、观测及迁移

公共路由按准确任务名分配；显式投递/装饰器/Beat路由优先，保留既有业务契约。未知任务进入celery，由background消费并限频记录诊断。仅声明新队列不能迁移已有积压，11,072条现场队列数据不能当作全部流量构成。

只读 `celery_runtime_report --workers --strict` 核对版本、本地注册、Beat最终路由、各节点完整回复、队列消费者数、实际并发、原生池实现与目标任务注册。保留专用消费者并纳入检查；未知指标输出null，不能当作0。注册诊断通过ContextVar和CLI入口保护避免触发周期表自动同步。

`celery_routes` 默认dry-run，仅修改明确ID列表的queue/exchange/routing_key，事务行锁、独占快照、恢复冲突校验。显式改路由会使上游周期表所有权指纹不再匹配，视为人工接管；不伪造或刷新所有权，不更改业务参数/周期/启停。回滚仍检查任务名及三个字段，避免覆盖后续修改。

公共日志使用项目celery_logger，稳定模板和惰性参数；只记录有界任务/队列标签、时间桶及状态，不记录参数、正文和异常详情。进程内计数每100事件或下次活动距上次超过60秒汇总，退出时尽力flush；这不是可靠审计总账，不能称为精确全局计数。排队时长扣除正常ETA等待，缺发布头/时钟偏差显式未知。

迁移先保留旧消费者、准备新消费者并验证路由，温和排空旧worker后切生产者和唯一Beat，所有重叠容量计入预算。回滚需继续消费新旧队列直至排空；禁止purge、批量重投和强杀繁忙任务。任务槽隔离不消除共享DB、CPU、内存和磁盘争用，不解决同池内部业务耗时问题。

## 验证与发布门槛

测试覆盖准确注册名、既有专用队列、CMDB导出/批量关联路由、四池与专用池总预算、ORMdry-run及恢复冲突、只读诊断、上游Beat所有权同步、启动空环境/重复/迁移失败，以及真实Redis隔离/伸缩/ETA/重试/软硬超时/回收。

`make test`、目标Linux镜像、全组件同时MAX峰值、升级重叠、真实任务时延和混合版本回滚必须单独记录结果；本机探针不能替代生产容量验收。未完成项保留在tasks.md，草稿PR不等于上线批准。详见implementation-evidence.md与review-report.md。
