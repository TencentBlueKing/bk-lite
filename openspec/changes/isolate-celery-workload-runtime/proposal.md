## Why

默认 Celery 队列共享执行槽，CMDB关联、导入导出和节点高频收敛会挤压监控告警。整机16–32GB同时承载全部组件，不能简单按模块增加常驻进程。

## What Changes

- 将默认工作负载拆为critical、notification、state、background四个有界弹性执行池，保留历史celery消费。
- 适配最新上游 `7fc417be88` 的182项准确任务名称；保留OpsPilot、报表渲染、补丁维护既有专用队列和消费者。
- 保留原生prefork、现有超时/回收/ACK/重试，统一校验四池MAX与专用消费者的总并发预算。
- 增加公共生命周期观测、只读诊断、Beat路由dry-run与恢复工具、部署和回滚说明。
- 不修改业务函数、模型、调度频率，不做业务算法、去重或补算优化。

## Capabilities

### New Capabilities
- `celery-workload-isolation`: 按负载职责隔离、统一MIN/MAX、既有消费者和执行策略保留。
- `celery-capacity-operations`: 资源预算、可观测、路由迁移和回滚。

### Modified Capabilities

无业务能力变更。

## Impact

公共Celery配置、默认worker启动方式、巡检与运维工具。完整安装由4个worker主进程变为7个；既有专用消费者并发计入预算。需要显式配置各池MIN/MAX及总上限、移除旧CELERY_CONCURRENCY。现场性能和容量未经测量，保持草稿，不直接发布。
