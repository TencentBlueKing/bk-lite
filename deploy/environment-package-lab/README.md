# 环境包业务链路隔离验收

仅用于已存在的 wx-test / `/opt/bklite-environment-test-20261113`，云区域 2 `Auto Executor validation 20261114`，C/D 两台 VM。本目录不是生产部署入口，不会在平台启动期运行。原平台、云区域 1 和原 Agent 不属于变更目标。

## 固化的修复

- 云区域的发送账号须具有 `vector`、`apm.traces.2` 发布和 reply inbox 接收权限；安装下载账号不能替代业务账号。
- Ansible 需要完整的 stream/consumer 管理、durable create、pull 和 ACK 权限，权限限定在本轮节点的具体 stream。配置保留其他账号原值。
- 产品 `server/apps/node_mgmt/support-files/collectors/Ansible-Executor.json` 默认 namespace 与 DLQ 按 `${node.id}` 隔离，避免不同节点复用同一个工作队列。`region.py` 仅迁移云区域 2 的自动生成默认配置，遇到自定义或共享配置拒绝覆盖。
- 使用标准中心 Vector 配置编译器和 `deploy/apm/otel/system.yaml`，部署独立 VictoriaLogs、VictoriaTraces、Vector 和 APM collector；无宿主端口发布，均有限额，存储使用独立命名卷。
- APM consumer 的 filter 遵循当前 receiver 的 `apm.traces.>` 契约，而 stream 仅接收 `apm.traces.2`。CA 是公有证书的独立只读副本，允许非 root collector 读取；没有放开私钥或凭据文件权限。
- `images.json` 校验已有镜像 ID，`--pull never` 禁止隐式替换；即使标签为 latest，也不能在校验时换成别的内容。

没有向 C/D 写手工组件配置。云区域环境变量和受控默认模板由平台正常下发，运行账号沿用原云区域 2 的私有凭据，未将平台管理员凭据发给 VM。中心消费端使用隔离 broker 的管理账号，生产最小权限账号设计不在这个固定实验脚本范围内。

## 已部署实例复验

在本机使用既有 SSH alias，先看变更预览（不输出凭据）：

```sh
ssh wx-test 'python3 /opt/bklite-environment-test-20261113/runtime/business/reconcile.py --plan'
```

重复部署（进程锁保护；配置无变化时不重建现有容器、不重写节点默认配置）：

```sh
ssh wx-test 'sh /opt/bklite-environment-test-20261113/runtime/business/apply.sh'
```

注入两台新日志和新 Trace，然后执行四个 Ansible 作业并验证最终结果：

```sh
ssh wx-test 'python3 /opt/bklite-environment-test-20261113/runtime/business/inject.py repeat'
ssh wx-test 'docker exec env-install-ca-api-20261113 python /test/runtime/business/verify.py repeat'
```

必须出现 `__BUSINESS_STORAGE_AND_ANSIBLE_VERIFIED__`。入口 ACK/HTTP 200 不算通过。结果核对日志正文与节点 IP、Trace/Span ID 与云区域、Ansible owner ID 与 stdout 主机名、退出码与成功终态。

仅查询本轮初始持久化结果，不产生作业：

```sh
ssh wx-test 'docker exec env-install-ca-api-20261113 python /test/runtime/business/verify.py persisted'
```

暂停并恢复**新建的隔离 APM 消费端**，检查积压与补消费（有副作用，仅用于这套测试实例）：

```sh
ssh wx-test 'python3 /opt/bklite-environment-test-20261113/runtime/business/recovery.py'
```

脚本用 finally 恢复消费端，不停止 Broker，不动原平台。成功标记为 `__TRACE_FILE_QUEUE_RECOVERY_AND_BUSINESS_VERIFIED__`。

日志使用默认 15044 Logstash 协议，注入器按 [Lumberjack 协议](https://github.com/logstash-plugins/logstash-input-beats/blob/main/PROTOCOL.md) 发送合成事件。Trace 使用默认 4318 OTLP/HTTP；不修改 VM 的监听或采集模板。

## 源码同步与测试

将本目录脚本、compose.yaml、system.yaml、images.json 同步到隔离目录 `runtime/business`；额外复制产品目录的 `Ansible-Executor.json` 到同目录，再执行 `apply.sh`。不复制本机凭据。远端需要已有私有云区域配置、镜像和测试数据库，`reconcile.py` 对目标身份、镜像、节点数量作前置检查。

本地：

```sh
python3 -m unittest discover -s deploy/environment-package-lab -p 'test_*.py' -v
python3 server/apps/node_mgmt/tests/test_ansible_executor_default_namespace.py
```

`system.yaml` 保持与标准 APM 系统配置一致；中心 Vector YAML 由 API 镜像内的产品编译器生成，不手写转发器替代产品。

## 数据和恢复范围

证据位于隔离主机 `evidence/business-20261115`。既有私有凭据源只留在该主机，不应放入 Git 或交付文档；环境变量传递和旧文件处理见文末。日志/Trace 保留 3 天；测试 JetStream 最大 64 MiB、保留 1 天。证据 JSON 保留查询结果，超过期限后应重新注入再验收。

可停止 `env-business-20261115` compose 项目的四个新服务回收计算资源，保留命名卷；不要执行 `down -v`。Broker 权限备份为 `config/nats.permissions-pre-business-20261115.json`，仅保留目标账号及原权限，回退时需比较后仅撤销本账号的新增权限。原 API 容器保留为 `env-install-api-pre-business-20261115`；模板回退也须限定云区域 2，不能批量覆盖用户配置。

## C/D 查询页面与告警链路

可用 `ENV_QUERY_SERVER_IMAGE=bklite/server:env-pr-20261116 bash apply-query.sh` 指定已构建的本机镜像；部署在任何写入前解析镜像 ID，并按镜像 ID 与配置判断更新。同标签重建会更新隔离容器，相同镜像与配置重复执行不重启。

新增 `apply-query.sh` 统一启用隔离 log/APM 模块、迁移隔离数据库（先备份）、部署独立 MinIO、Beat、通知回执接收器，并创建 C/D 专属应用及日志分组。模块 URL/设置放在隔离 runtime，未修改原平台配置。MinIO 有独立卷、无宿主端口，采用已验证的凭据启动方式与就绪门禁；失败容器保留用于诊断。重复执行保持现有容器 ID 和启动时间。

```sh
ssh wx-test 'bash /opt/bklite-environment-test-20261113/runtime/business/apply-query.sh'
```

先在页面登录 `http://10.10.248.31:18300`。日志分组为“C/D 实际日志”，APM 应用为“C/D 查询告警验证”，服务为 `cd-c` / `cd-d`。

复验触发（只生成 C/D 合成测试流量）：

```sh
ssh wx-test 'docker exec env-install-ca-api-20261113 python /test/runtime/business/query-fixtures.py --policies'
ssh wx-test 'python3 /opt/bklite-environment-test-20261113/runtime/business/query-inject.py alarm'
```

等待约 2 分钟，在日志/APM 的“事件 → 告警”看各 2 条活跃告警及通知成功。日志查询 `verification:="CD-QUERY"`，Trace 路由 `GET /cd-validation`。异常延迟 500 ms，阈值 100 ms。

恢复正常流量，隔 30 秒再执行一次，以覆盖调度边界：

```sh
ssh wx-test 'python3 /opt/bklite-environment-test-20261113/runtime/business/query-inject.py recovery'
```

等待约 2 分钟：APM 自动恢复到 1 ms，历史告警详情可见恢复事件。**日志模块现有语义是人工关闭**：在页面关闭本轮两条日志告警，核查历史记录及关闭通知，不把它写成自动恢复。

```sh
ssh wx-test 'docker exec env-install-ca-api-20261113 python /test/runtime/business/query-verify.py'
ssh wx-test 'docker exec env-install-ca-api-20261113 python /test/runtime/business/query-snapshots.py'
ssh wx-test 'docker exec env-install-ca-api-20261113 python /test/runtime/business/query-fixtures.py --disable'
```

必须出现 `__QUERY_ALERT_LIFECYCLE_VERIFIED__` 和 `__S3_SNAPSHOTS_READ_BACK__`。`query-verify.py` 从最新 `alarm-traffic.json` 确定本轮，再查询新建告警及其事件、逐条匹配回执，成功后将告警/事件 ID 写入 `final-verification.json`；校验开始即清除旧成功标记。快照复验仅查询这份本轮结果中的告警 ID，保留历史记录；仍要求 C/D 各一条日志快照及各自 APM 触发/恢复快照完整可读。缺失本轮证据或快照必须失败，不能回退使用历史成功结果。最后一条仅停用本轮测试策略，保留数据供页面查询。通知走真实 SystemMgmt/NATS 调用，但接收目标是隔离回执服务；未测试企业微信、邮件、短信或统一告警中心接收后的处理。回执交付文件剔除内部签名；健康探测不计入业务通知数。

查询告警证据：`evidence/query-alert-20261115`。脚本内沿用创建日期，实际完整验收日期为 2026-11-16。先同步本目录脚本到隔离 `runtime/business` 再运行入口；所有入口限定这套既有实验环境，不能直接作为任意环境生产安装器。


重复验收的身份链：先完成本轮日志关闭/APM 恢复，再执行 `query-verify.py`，然后执行 `query-snapshots.py`。在已配置 Playwright 的隔离浏览器测试环境运行 `query-ui-recovery.py`，该脚本读取同一份 `final-verification.json`，按 `data-row-key` 中的告警主键定位 C/D 四条历史告警，必要时翻页，并分别检查状态和通知状态。旧结果的 run_id 不匹配最新注入时拒绝执行，不按同名策略取第一条。

通知协议按现有产品实现核验：APM 通过 outbox 的 `event_key` 映射数据库事件 ID；日志协议未携带事件主键，通过本轮事件对应的告警 external_id、动作、事件时间和资源/策略 ID 匹配。证据补充数据库 alert_id/event_id，不伪造协议字段。其他轮次回执忽略，本轮缺失、重复、错误事件 key 或时间均失败。同步脚本时需一起复制 `query_run.py`。

测试策略停用后再次启用时，`query-fixtures.py --policies` 会把这条 C/D 日志策略的扫描游标设为本轮开始时间，保留全部历史告警和事件，避免先补扫停用期间的旧窗口。已经启用时重复执行保留游标；不修改产品扫描器及其他策略。每轮完成后先执行 `--disable`，下轮再启用并注入新流量。

恢复页面验收按本轮告警主键定位历史行并核查已通知状态；日志在列表和详情验证关闭状态，APM 在该行打开的详情抽屉验证“已恢复”（APM 列表无恢复状态列）。不能用页面上其他告警的恢复文本替代本轮详情。

日志查询页面验收使用本轮注入时间前 60 秒、后 120 秒的绝对窗口，等待两个当前标记实际渲染（最多 60 秒）；不以固定休眠代替加载完成，也不受重跑时最近 15 分钟窗口影响。

## 凭据传递与旧文件处理

既有 config/ui-server.env、config/query-minio.json 和 config/nats.conf 保持为私有凭据源。部署不再生成 query-minio.env、query-server.env 或 pipeline.env，Docker 覆盖项与 Compose 变量仅经子进程环境传递，命令行只含变量名。Docker 仍保存容器所需环境配置，Docker 管理权限须按凭据访问权限控制。

reconcile.py --apply 现在在同一进程准备配置、执行区域对账并启动 Compose，apply.sh 仍持有部署锁。不要绕过入口单独执行 docker compose up，否则缺少凭据环境。MinIO 继续复用既有私有 JSON，重复执行不轮换密码。

Broker 新备份为 config/nats.permissions-pre-business-20261115.json，仅含目标账号名和原权限，不复制密码。回退时对比后只撤销该账号新增权限，不整文件覆盖 nats.conf。

旧版本的派生 env 文件和全量 Broker 备份不由新代码自动删除。维护者确认旧入口及挂载停用后可单独安排清理；本次源码修复不执行现场清理、部署、重启或凭据轮换。
