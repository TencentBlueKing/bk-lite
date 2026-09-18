# 配置采集凭据类型分类与内置目录

日期：2026-09-16，按已确认的 SSH／WinRM 分类方案更新。覆盖社区 45＋企业 73＝118 个入口。

## 当前规则

- 2026-09-17：网络设备配置文件改为 `network/ssh`。当前 Scrapli 插件只消费密码认证，因此已有凭据仅展示 SSH 密码凭据，快捷创建同样限定密码模式；SSH／Telnet、端口、特权密码由任务补充。执行前拒绝不支持的私钥凭据。旧平台账户引用可沿用并主动切换 SSH，不修改存量任务。

- HTTPS 平台账户 `platform_api` 仅内置 `username`、`password`。`port`、`verify_tls` 从系统管理类型定义移除；端口和 TLS 校验由采集任务表单提供（vCenter 使用 `ssl`），执行时只合并凭据认证字段，不使用凭据库残留的连接参数。刷新类型不改写存量凭据；后续编辑保存按现有机制移除已废弃字段并保留未修改的密码。
- JOB 使用真实远程执行协议的凭据：SSH 或 WinRM；协议入口按实际认证机制使用数据库账户、SNMP、API 账户、Token、AK/SK 等。
- 对象分类与认证类型分开：例如 Informix JOB 是“数据库／SSH”，Cisco FC 是“网络／SSH”。不能由对象名称推导连接协议。
- 57 个 JOB 入口中，56 个走 SSH；PC Windows 走 WinRM、macOS 走 SSH。IIS 虽使用 PowerShell 脚本，当前清单与执行器仍是 SSHPlugin，不能只看脚本后缀改成 WinRM。
- Agent 是 JOB 的目标执行路径；是否可省略登录凭据取决于目标 Agent 是否可用，不因留空就自动接入。
- 一次性认证继续使用原表单，端口和其他动态字段仍属于任务。选择 SSH 已有凭据可以使用密码或私钥及私钥口令。

## 全 118 入口按分类和类型汇总

下表为新建任务的查询类型；旧 JOB 的用户名密码引用仅作存量兼容。PC 在默认 WinRM 一行计数，macOS 复用 SSH，不重复计入总数。

| 对象分类 | 内置类型 key | 入口数 | 逐项插件 ID |
|---|---|---|---|
| 独立接入／无需手工凭据 | — | 2 | `k8s_cluster`、`ip_discovery` |
| 主机 | SSH `ssh` | 5 | `docker`、`host`、`config_file`、`physcial_server`、`hmc` |
| 云平台 | HTTPS 平台账户 `platform_api` | 12 | `vmware_vc`、`zstack`、`h3c_cas`、`winsphere`、`smartx`、`manageone`、`fusioncompute`、`sangforhci`、`sangforscp`、`nutanixhci`、`inspurincloudrail`、`fusioninsight` |
| 云平台 | OpenStack 账户 `openstack` | 1 | `openstack` |
| 网络 | SNMP `snmp` | 3 | `network`、`f5`、`security_device` |
| 网络 | SSH `ssh` | 3 | `brocade_fc`、`cisco_fc`、`network_config_file` |
| 数据库 | 用户名密码 `sql` | 15 | `mysql`、`postgresql`、`mssql`、`oceanbase`、`highgo`、`couchbase`、`sap_hana`、`iris`、`tongrds`、`tdsql`、`gbase8a`、`greenplum`、`kingbase`、`opengauss`、`vastbase` |
| 数据库 | API Token `token` | 1 | `influxdb` |
| 数据库 | SSH `ssh` | 13 | `redis`、`mongodb`、`es`、`hbase`、`informix`、`sybase`、`mycat`、`redis_sentinel`、`gbase8s`、`oscar`、`dameng`、`db2`、`tidb` |
| 存储 | HTTPS 平台账户 `platform_api` | 12 | `storage`、`dell_unity`、`netapp_ontap`、`ibm_storwize`、`emc_symmetrix`、`hds_vsp`、`pure_array`、`netapp_cluster`、`oraclezfs`、`infinidat`、`dell_powerstore`、`hp_3par` |
| 存储 | AK/SK `cloud` | 2 | `ibm_ds`、`xsky` |
| 存储 | SNMP `snmp` | 2 | `macrosan`、`tape_library` |
| 云平台 | AK/SK `cloud` | 4 | `aliyun_account`、`qcloud`、`hwcloud`、`aws` |
| 云平台 | OAuth 客户端 `oauth_client` | 1 | `azure` |
| 主机 | IPMI `ipmi` | 1 | `physcial_server_ipmi` |
| 主机 | Redfish `redfish` | 2 | `physcial_server_redfish`、`server_bmc` |
| 主机 | WinRM `winrm` | 1 | `pc` |
| 中间件 | SSH `ssh` | 36 | `nginx`、`minio`、`zookeeper`、`kafka`、`consul`、`etcd`、`rabbitmq`、`tomcat`、`apache`、`activemq`、`iis`、`tuxedo`、`memcached`、`rocketmq`、`openresty`、`squid`、`haproxy`、`keepalive`、`spark`、`ibmmq`、`tonglinkq`、`tonggtp`、`ihs`、`cics`、`hdfs`、`yarn`、`storm`、`bes`、`apusic`、`inforsuite_as`、`ceph`、`jboss`、`jetty`、`tongweb`、`weblogic`、`websphere` |
| 中间件 | 用户名密码 `sql` | 2 | `nacos`、`ambari` |

ZStack、IBM DS、XSKY 的类型仍是旧声明，真实认证消费未确认；上表列出当前绑定，不将其计为认证契约确认。9 项缺配置采集体、19 项 JOB 仅基础探测、2 项运行副本缺产物等边界见[完整逐项报告](cmdb-collection-script-credential-audit-2026-09-16.md)。本轮只改变认证类型绑定，不把这些采集实现缺口标为完成。

## 本轮内置变更

SSH `ssh` 的分类由主机扩展到主机、网络、数据库、中间件。字段继续使用已有定义：`auth_method`、`username`，以及密码模式的 `password` 或私钥模式的 `private_key`／可选 `passphrase`。WinRM 保持主机分类及 `username/password`。

共复用 11 种类型；系统管理另保留 network_cli 和 gateway_secret，共 13 个内置类型。不新增重复类型，不更名 sql，不改已有真实凭据的类型。sql 原有分类保留供旧引用使用。

| 新建 SSH JOB 绑定 | 数量 | 原绑定（仅存量兼容） |
|---|---|---|
| `host/ssh` | 5 | `host/sql` |
| `network/ssh` | 2 | `network/sql` |
| `database/ssh` | 13 | `database/sql` |
| `middleware/ssh` | 36 | `middleware/sql` |

## 存量与下发

1. 新建任务 tree 仅返回实际类型；SSH JOB 的已有凭据仅查询 SSH。
2. 旧用户名密码引用保留原 ID，在执行前按原 sql 认证 Schema 校验；仍保留权限、停用状态和保存类型一致性校验。不会从库中解密后写回任务。
3. 编辑旧引用显示原凭据名称，并提供“改用 SSH 凭据”；用户切换时清除旧引用 ID，保留端口，重新选择 SSH 凭据。旧版本未保存 vault_type_key 的 JOB 引用同样兼容回显。
4. SSH 类型按密码／私钥条件字段校验后下发 username、password 或 private_key、passphrase；敏感值只放 env_config，配置正文使用环境变量引用。多候选各有独立变量。
5. PC Windows 只接受 WinRM，macOS 只接受 SSH，不为 PC 新增 sql 兼容。MySQL 等协议入口不接受 SSH 凭据。
6. `vault_credential_id` 是系统管理凭据引用；`credential_id` 继续是任务候选标识。一次性认证不读取凭据库。

MySQL／PostgreSQL 在当前 118 入口中是协议采集。历史记录即使 driver 标记 job，现有 NodeParams 仍为数据库直连参数类，兼容分支不把这类旧记录强行改成 SSH。

## 初始化与验证

当前开发库已执行现有 `seed_builtin_types()` 同步 SSH 分类，不修改真实凭据或存量任务。无需新增 migration。其他环境部署后执行：

```sh
python manage.py shell -c "from apps.system_mgmt.services.credential_service import seed_builtin_types; seed_builtin_types()"
```

测试包含全部 118 入口，56 个 SSH JOB 的密码、双私钥候选、旧 sql 引用（含未保存类型的旧引用），以及 PC WinRM／macOS SSH、协议类型拒绝混用、前端旧引用换选。测试只验证认证及参数链路，未连接真实设备。


### 本轮新鲜验证结果

| 检查 | 结果 |
|---|---|
| 后端社区＋企业 118 入口、类型匹配、节点参数、PC 与旧引用兼容 | 1372 通过；2 个无需凭据入口跳过；2 个已知企业运行副本产物缺失预期失败；1 个 SQLite JSON contains 基线限制排除 |
| 前端表单、Picker、旧引用回显及切换 | 14 文件，338 通过 |
| Stargazer 实际请求字段、Agent 路由、PC、SNMP 与插件回归 | 191 通过 |
| TypeScript／修改的前端 ESLint／两个仓库 diff --check | 通过 |
| 开发库内置分类 | 13 类型同步，缺失绑定为 0，自定义类型与真实凭据记录不变 |

浏览器独立刷新仍列出旧 sql 凭据。进一步确认 8011 服务确为本仓库 server，运行在 PyCharm 的 `runserver --noreload` 调试进程中，尚未加载新映射。需要在 PyCharm 重启该后端，再刷新前端；没有停止用户调试进程或覆盖原页面表单。无需再次初始化，不将此次页面观察记为新版 UI 类型查询已通过。
