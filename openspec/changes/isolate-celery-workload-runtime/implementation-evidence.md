# 最新上游适配与验证记录（2026-10-30）

## 实施结果

基于刷新后的 TencentBlueKing/bk-lite master `7fc417be88`。仅将原默认worker拆成critical、notification、state、background四池，保留OpsPilot、报表、补丁维护既有专用消费者、原生prefork、任务软硬超时、200任务/512000KiB默认回收及ACK/retry。

最新静态清单182项，准确处理显式name及queue；截图中的导出、批量关联、节点收敛等任务已找到源码。四池MAX、既有专用并发、所有同构副本及升级重叠纳入同一总预算；完整安装7个worker主进程，容量必须实测，不提供并发1够用的承诺。

默认worker/Beat由公共解析器生成，保留上游migrate失败门禁、batch_init和可选进程清理；生成前使用与实际专用消费者一致的shell导出配置。管理命令只读注册不触发周期表同步；ORM路由工具默认dry-run、显式ID名单、快照与冲突恢复。业务任务函数、模型、周期未修改。

## 新鲜验证

| 项目 | 结果 |
|---|---|
| TDD | 先验证旧兼容池取消超时、预算遗漏专用池、旧路由清单、项目日志规范的失败，再适配修复 |
| 公共配置/路由/观测/诊断/ORM/启动及上游Beat同步 | 110 passed；独立Django/Beat SQLite环境，未加载全部业务应用 |
| 覆盖率 | 91.85%（810语句、66未覆盖），范围为公共runtime、core.celery、Celery配置和两个管理命令；不是全仓覆盖率 |
| 真实Redis / prefork | 5 passed（32.51秒）：隔离、扩缩容、ETA/重试/历史队列、原生软硬超时、任务数阈值回收 |
| 格式/静态 | 触及文件black/isort/flake8、bash语法、diff空白及OpenSpec strict校验通过；仓库pre-commit全部通过 |
| 平台边界 | 本机macOS专用探针显式fork，不能替代目标Linux镜像的全应用验证；不连接生产broker、不投递真实业务或远端作业 |

## 未完成的发布门槛

- `cd server && make test` 实际执行，仍在MLOps初始化因缺少可选依赖mlflow失败；没有隐藏业务测试或修改业务代码绕过。
- 本机Docker此前拉镜像返回containerd元数据I/O错误；未重置Docker，目标Linux测试仍待完成。
- 生产commit、启用模块、副本数、实际注册/生产者/持久化Beat路由仍需现场核对；当前源码不是生产状态证明。
- 16–32GB全组件同时MAX峰值、升级重叠、真实任务排队分位数和积压排空/回滚演练尚未执行。回收阈值不是单任务硬内存上限。

当前交付为经过审查和本地验证的草稿PR，尚未达到生产发布或OpenSpec归档条件。没有部署生产、清空消息、批量重投或修改业务调度。
