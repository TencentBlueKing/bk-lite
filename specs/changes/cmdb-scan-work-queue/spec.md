# CMDB 扫描工作队列（协议先打、JOB 分批）

Status: ready

## Problem Statement

扫描触发时把网络、主机、数据库、中间件全部同时接纳给 Stargazer。JOB 族（主机 SSH、7 种中间件脚本）会把整段 IP 一次性打到约 20 个 Ansible 槽上；交换机 SSH 挂满 `execute_timeout` 后，真正的主机/中间件永远排不到。任务墙钟上限 2 小时还会在队列还没跑完时把执行标成超时，剩下的批次被丢掉。

## Solution

触发时只接纳协议族（网络 SNMP、数据库、物理机、InfluxDB）。JOB 进入执行级工作队列：按约 8 个 IP 切批，同一时刻只飞一批；网络 SNMP 成功的地址不再打 SSH；若勾了主机，中间件只打主机成功的地址。可选 TCP 监听端口探测用来少打明显没开端口的中间件类型，探测全空则不过滤、照样切批跑完。整任务以队列排空为完成条件，不因 2 小时墙钟丢掉剩余批次；单批卡住则跳过该批继续下一批。

## User Stories

1. As a CMDB 管理员, I want 一次勾选网络、主机、中间件、数据库的大网段扫描能跑完, so that 不会因为交换机占满 SSH 槽而漏掉主机和中间件。
2. As a CMDB 管理员, I want 交换机 SNMP 命中后不再对它做主机 SSH, so that JOB 时间花在真正的服务器上。
3. As a CMDB 管理员, I want 同时勾主机和中间件时只在主机发现成功的地址上跑中间件脚本, so that 不会对空地址连打 7 种 JOB。
4. As a CMDB 管理员, I want 任务可以跑很久但最终收口而不是超时截断, so that 255 地址、多种中间件也不会缺批。

## Implementation Decisions

- 协议族触发时一次接纳；JOB 族（`host` 与 `SCAN_MIDDLEWARE_TYPES`）进入 `ScanExecution.schedule` 队列。
- JOB 批次大小 8，同执行进行中只接纳 1 个 JOB `family_run`。同一模型多批用 `ScanFamilyRun.batch_index` 区分。
- 网络 SNMP `success` 地址从后续 JOB 目标中剔除。勾了主机则先排主机批次；主机跑完后，中间件只对主机 `success` 地址入队。只勾中间件则对（剔除 SNMP 后的）剩余地址入队。
- 中间件入队前对候选地址探测常见监听端口（nginx 80/443、tomcat 8080、kafka 9092、zookeeper 2181、rabbitmq 5672/15672、consul 8500、etcd 2379）。至少探到一个开放端口时按类型过滤；全部失败或全关则不过滤，仍按类型×切批跑完。端口探测是调度过滤器，发现本体仍是 JOB 脚本。
- JOB 下发带 `ip_precheck=True`。不把 7 种脚本打进同一次 SSH，不改 Stargazer `execute_timeout`。中间件 SSH 端口只表示登录端口；若填成 Nginx/Consul 等监听端口（80/8500 等），接纳时改回 22，避免 access_probe 拿 HTTP 口当 SSH。
- `poll_scan_finalize`（含凭据回传踢收口）在队列未排空时不得 `completed` / `timed_out`。协议阶段超过原 `deadline_at` 则转入 JOB，不丢队列。当前 JOB 批超过本批 `batch_deadline_at` 则跳过并接纳下一批。
- 凭据不进 `schedule`；接纳时仍从任务凭据池解析（中间件可回退主机 SSH / Agent 占位）。
- 收口拉 VM 指标只为把通道口 22 拆成 listen_port，并带上脚本里的配置/安装路径。JOB 已 success 时，指标空不得删 ScanHit。收口只查一次 VM，不 `sleep` 赌窗口；路径字段晚到时任务仍标完成，由 Celery 按退避补齐 snapshot，直到路径可读或超过 VM 1h 回看。

## Testing Decisions

外部行为缝：`trigger_scan_execution` 与 `poll_scan_finalize`。不启真实 Stargazer，不测脚本内部，端口探测可替换。

- 协议族（mysql+network）触发仍一次接纳两枪。
- 只勾中间件：触发只接纳第一批第一个类型，不是 7 枪同时打出；排空后 7 种类型都有 family_run，不含 redis。
- 空中间件池第一批仍带 Agent 占位凭据。
- 网络+主机：触发只接纳 network；网络收齐后 poll 接纳 host，且 SNMP success 地址不在 host 的 `cmdbhosts`。
- 主机+中间件：触发先接纳 host；主机 success 之后 poll 才接纳中间件，且复用主机 SSH。
- 网络收齐但 JOB 未入队时 poll 不得 completed。
- 协议 deadline 已过但仍有 JOB：poll 转入 JOB，不得 timed_out 丢掉队列。
- 仅网络且 received>=target：poll 仍 completed（无 JOB 队列）。
