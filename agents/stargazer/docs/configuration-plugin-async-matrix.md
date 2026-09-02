# Stargazer 配置采集插件异步矩阵

更新日期：2026-08-20

本文记录 `plugins/inputs` 中配置采集插件的真实 I/O 模型。判断依据是底层网络依赖，不能只看
入口是否写成 `async def`。

## 状态定义

| 状态 | YAML `execution_mode` | 含义 |
| --- | --- | --- |
| 原生异步 | `async` | 底层网络依赖提供异步 I/O，采集路径直接 `await`，不把整轮网络调用放入线程 |
| 同步隔离 | `sync` | 底层 SDK 为同步实现，公开异步入口使用线程隔离；不能称为原生异步 |
| 远程异步 | `remote` | Stargazer 通过异步 NATS 提交和等待，脚本在独立远程执行端运行 |

线程用于首次模块导入、本地文件读取或 CPU 转换，不等同于同步网络采集；但
`requests`、同步数据库驱动、Netmiko、pyVmomi、pyghmi 和同步云 SDK 的网络调用不得标记为
`async`。

## Protocol executor

| 插件 | 是否原生异步 | 异步方法/当前依赖 | 说明 |
| --- | --- | --- | --- |
| `aliyun` | 否 | `asyncio.to_thread` + 阿里云同步 SDK/`oss2` | 同步隔离；Tea 异步接口、ECS 和 OSS 尚未完成等价迁移 |
| `fusioninsight` | 是 | `httpx.AsyncClient.request()` | REST 登录、集群和主机采集均直接 `await` |
| `gbase8a` | 是 | 继承 `MysqlInfo`，使用 `aiomysql` | MySQL 兼容协议，异步连接和 SQL |
| `greenplum` | 是 | 继承 `PostgresqlInfo`，使用 `psycopg.AsyncConnection` | PostgreSQL 兼容协议 |
| `hwcloud` | 否 | `asyncio.to_thread` + 同步 `CMPDriver` | 同步隔离；当前华为云 SDK 没有等价 async client |
| `influxdb` | 是 | `httpx.AsyncClient.get()` | InfluxDB v1/v2 HTTP 路径直接 `await` |
| `ip` | 是 | `asyncio.open_connection()`、`icmplib.async_ping()`、`asyncio.create_subprocess_exec()` | TCP、ICMP 和 ARP 辅助查询均不阻塞事件循环 |
| `kingbase` | 是 | 继承 `PostgresqlInfo`，使用 `psycopg.AsyncConnection` | PostgreSQL 兼容协议 |
| `mssql` | 否（线程型 await） | `aioodbc` | 调用方使用 `await`，但 aioodbc 底层通过线程执行 ODBC，按 `sync` 管理 |
| `mysql` | 是 | `aiomysql.connect()`、异步 cursor | protocol 为异步；同插件 job executor 为远程异步 |
| `network` | 是 | `pysnmp.hlapi.asyncio.getCmd/nextCmd` | SNMP GET/Walk 直接 `await`；`SnmpEngine` 由 `core.infra.snmp_engine_pool` 按凭据作用域进程级共享，空闲或进程退出时才关闭 dispatcher |
| `network_config_file` | 是 | `scrapli.AsyncScrapli` + `asyncssh` transport | 原 Netmiko 整轮线程包装已移除；保持 host key 严格校验 |
| `network_topo` | 是 | `pysnmp.hlapi.asyncio.getCmd/nextCmd/bulkCmd` | SNMP 拓扑采集和 fallback 均直接 `await`，与 `network` 共用同一个共享 `SnmpEngine` 池 |
| `oceanstor` | 是 | `httpx.AsyncClient` | 登录、分页采集和登出均直接 `await` |
| `opengauss` | 是 | 继承 `PostgresqlInfo`，使用 `psycopg.AsyncConnection` | PostgreSQL 兼容协议 |
| `oracle` | 是 | `oracledb.connect_async()` | 仅 Oracle Thin async 模式属于原生异步 |
| `physcial_server` protocol | 否 | `asyncio.to_thread` + `pyghmi` | IPMI 同步隔离；默认 executor 仍是 remote job |
| `postgresql` | 是 | `psycopg.AsyncConnection.connect()`、异步 cursor | protocol 为异步；同插件 job executor 为远程异步 |
| `qcloud` | 否 | `asyncio.to_thread` + Tencent/COS 同步 SDK | 同步隔离；TC3、COS 异步 HTTP Adapter 尚未完成等价迁移 |
| `vastbase` | 是 | 继承 `PostgresqlInfo`，使用 `psycopg.AsyncConnection` | PostgreSQL 兼容协议 |
| `vmware_vc` | 否 | `asyncio.to_thread` + `pyVmomi` | SOAP SDK 同步隔离；需 vSphere REST 覆盖后才能原生异步 |

当前 21 个 protocol executor 中：15 个原生异步，6 个同步隔离。同步隔离项继续受到
`MAX_ACTIVE_TARGETS` 全局边界保护，不新增插件级并发参数。

## Enterprise protocol executor

| 插件 | 是否原生异步 | 异步方法/当前依赖 | 说明 |
| --- | --- | --- | --- |
| `sangforscp` | 是 | `httpx.AsyncClient.stream()` | RSA 加密在线程中执行；登录、分页、重试和响应流读取均原生 `await`。单次完整快照共用 300 秒总预算，并限制页数、对象数、单响应与总响应字节；任一阶段失败不返回半截快照 |

Sangfor 配置采集不再调用同步 `requests.Session`。`legacy_tls.py` 仍为旧监控指标链路提供
TLS 1.0/1.1 兼容，不能据此把配置采集判定为同步。配置采集使用相同的 legacy SSL context，
但连接由 `httpx.AsyncClient` 管理并在每次目标采集结束时关闭。

## Job executor

job 插件通过 `SSHPlugin.list_all_resources()` 调用异步 `nats_request()`。Stargazer 的事件循环只
负责异步提交和等待；脚本在远端 executor 的独立进程中同步执行，因此属于远程异步，不是
本地假异步。

| 插件 | 状态 | 异步方法 |
| --- | --- | --- |
| `activemq` | 远程异步 | `SSHPlugin` → `await nats_request()` |
| `apache` | 远程异步 | 同上 |
| `ceph` | 远程异步 | 同上 |
| `config_file` | 远程异步 | `ConfigFileInfo` → `await nats_request()` |
| `consul` | 远程异步 | `SSHPlugin` → `await nats_request()` |
| `dameng` | 远程异步 | 同上 |
| `db2` | 远程异步 | 同上 |
| `docker` | 远程异步 | 同上 |
| `es` | 远程异步 | 同上 |
| `etcd` | 远程异步 | 同上 |
| `haproxy` | 远程异步 | 同上 |
| `hbase` | 远程异步 | 同上 |
| `host` | 远程异步 | `HostInfo` 继承 `SSHPlugin` |
| `iis` | 远程异步 | `SSHPlugin` → `await nats_request()` |
| `jboss` | 远程异步 | 同上 |
| `jetty` | 远程异步 | 同上 |
| `kafka` | 远程异步 | 同上 |
| `keepalived` | 远程异步 | 同上 |
| `memcached` | 远程异步 | 同上 |
| `minio` | 远程异步 | 同上 |
| `mongodb` | 远程异步 | 同上 |
| `mysql` job | 远程异步 | `SSHPlugin` → `await nats_request()` |
| `nginx` | 远程异步 | 同上 |
| `openresty` | 远程异步 | 同上 |
| `pgsql` | 远程异步 | 同上 |
| `physcial_server` job | 远程异步 | `PhyscialServerInfo` 继承 `SSHPlugin` |
| `postgresql` job | 远程异步 | `SSHPlugin` → `await nats_request()` |
| `rabbitmq` | 远程异步 | 同上 |
| `redis` | 远程异步 | 同上 |
| `rocketmq` | 远程异步 | 同上 |
| `spark` | 远程异步 | 同上 |
| `squid` | 远程异步 | 同上 |
| `tidb` | 远程异步 | 同上 |
| `tomcat` | 远程异步 | 同上 |
| `tongweb` | 远程异步 | 同上 |
| `tuxedo` | 远程异步 | 同上 |
| `weblogic` | 远程异步 | 同上 |
| `websphere` | 远程异步 | 同上 |
| `zookeeper` | 远程异步 | 同上 |

## 未注册目录

以下目录没有 `plugin.yml`，当前不会被统一配置采集运行时解析：

| 目录 | 当前实现 |
| --- | --- |
| `aws` | 空目录 |
| `highgo` | 同步 `psycopg2`，启用前应复用异步 PostgreSQL Adapter |
| `tdsql` | 同步 `pymysql`，启用前应复用异步 MySQL Adapter |
| `nacos`、`server_bmc` | 同步 `requests`，启用前应改用 `httpx.AsyncClient` |
| `ambari`、`couchbase`、`iris`、`oceanbase`、`sap_hana`、`tongrds` | 占位实现，尚无真实采集链路 |

## 维护规则

1. 新增或修改 protocol executor 时，必须同步更新本矩阵和
   `tests/test_plugin_execution_metadata.py`。
2. `execution_mode: async` 的 Adapter 不得把整轮网络采集放进 `to_thread` 或
   `run_in_executor`。
3. 同步 SDK 必须标记为 `sync` 并在插件内部隔离，不能阻塞 `PluginExecutor` 所在事件循环。
4. job executor 保持 `remote`，不得因为远端脚本是同步 shell 就改成 `sync`。
5. 插件改造后必须验证输出契约、超时、取消、连接释放和凭据不进入日志。
6. 全局容量继续只使用 `MAX_ACTIVE_RUNS`、`MAX_ACTIVE_TARGETS`、`TARGET_TASK_WINDOW`。
