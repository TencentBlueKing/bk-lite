# 配置采集页面与凭据后端交叉核对（2026-09-24）

> 后续进展：本报告保留最初审计现场。七个平台的连接参数及异步执行问题已修复并通过本地链路测试，最新设计与真机验收状态见 [七个平台测试记录](cmdb-seven-platform-credentials-2026-09-24.md)。


## 范围与结论

当前社区版与企业版合并目录共有 **115 个入口**。其中 **112 个入口**接入凭据，逐项执行手动填写和选择系统凭据两条路径，共 **224 组创建、编辑、存储、下发回放**；另 3 个入口不走该凭据选择路径。历史 `collection_original_forms.json` 有 118 项，新增 SSL 证书及移除/隐藏 brocade_fc、cisco_fc、f5、server_bmc 后已经不能代表当前目录，本次以运行时代码导出为准。

**同类问题确实存在，不能只修深信服 HCI 的白名单。** 本次修复以下问题：

1. HCI、FusionInsight、华为存储的严格校验漏掉服务端生成的 `credential_version`，导致创建/编辑报“不支持字段”。保留严格未知字段检查，仅允许内部版本字段。
2. vCenter 回填把凭据池当作单个对象读取，非默认端口和 SSL 设置被覆盖；修复回填，并保留候选 ID。
3. IPMI 等经通用格式化方法的页面丢失 `credential_id`，引用凭据编辑时无法稳定对应旧候选；公共构造方法保留 ID。
4. 平台 API 页面重复发送 `password` 与 `accessSecret`，部分模型的加密/脱敏字段只覆盖其中一套。当前页面仅发送规范用户名/密码；18 个受影响企业对象补齐历史别名与规范字段的加密/接口掩码。旧数据在重新保存时加密，本次未对现有数据库批量回写。
5. SmartX `source`、FusionCompute `user_type` 在手动模式构造/回填时丢失；补齐对应控件和往返映射。
6. IBM DS、XSKY 手动 AK/SK 使用 camelCase，通用下发器读取 snake_case，导致密钥没有下发；统一两套输入字段。
7. OpenStack、SmartX、ManageOne 历史任务保留旧 AK/SK 别名时，修改规范密码仍优先使用旧别名；下发时优先使用当前规范字段，保留旧任务回退读取能力。

## 仍存在的页面/采集器缺口

以下 **7 个入口**的创建、凭据引用和秘密下发可以通过，但连接选项与采集器能力不一致。两种凭据模式都受影响；本次没有将这部分标成修复完成，也没有修改采集器的 TLS 策略或厂商连接协议。

| 入口 | 已核对的缺口 |
|---|---|
| `openstack` | 端口/TLS 未下发；采集器也未消费 |
| `smartx` | 端口未下发；HTTPS 下关闭 TLS 被采集器拒绝 |
| `manageone` | 端口/TLS 未下发；CMP 调用无对应参数 |
| `fusioncompute` | TLS 未下发；采集请求固定 verify=False |
| `nutanixhci` | 端口/TLS 未下发；请求固定 verify=False |
| `inspurincloudrail` | 端口/TLS 未下发；请求固定 verify=False |
| `azure` | OAuth/SDK 路径不消费通用端口/TLS 控件 |

证据：`server/apps/cmdb/node_configs/cloud/_cloud_base.py`，`enterprise/server/apps/cmdb_enterprise/collect/{smartx,openstack,manageone,fusioncompute,nutanixhci,inspurincloudrail,azure}.py`，及 `enterprise/agents/stargazer/enterprise/plugins/inputs/` 中对应采集器。应按各采集器的真实支持范围补齐连接选项，或移除不支持的页面控件；不能仅让服务端收下字段就认为已生效。

另有 **12 个入口的采集体尚未实现**：`zstack`、`ibm_ds`、`xsky`、`couchbase`、`sap_hana`、`iris`、`tongrds`、`ambari`、`ibm_storwize`、`emc_symmetrix`、`oraclezfs`、`infinidat`。当前对应企业采集器（或 `account_inventory.py` 基类）的 `list_all_resources` 明确抛出 `NotImplementedError`。凭据参数回放通过不改变该现状。

以下差异已确认属于正常转换：vCenter/H3C/WinSphere/SCP 的布尔参数为模板需要转换为字符串；InfluxDB 的 `scheme` 转成 `ssl`；PC 的 scheme/证书校验转成任务级 `winrm_*` 参数，认证方式固定 NTLM。

## 逐入口清单

“通过”只表示实际页面格式化请求经真实服务格式化、序列化器、ORM 加密保存、引用解析、NodeParams 生成配置，并完成编辑回放。**没有向真实设备下发或连接设备。** 权限/资产查询、节点以及 SystemMgmt 的跨服务调用由测试替身隔离；引用类型字段继续经过真实内置 schema 校验。表中列出测试所用页面字段分支（SNMP 使用 v3 authPriv，PC 使用 Windows）；其它认证分支依赖既有专项测试，不宣称穷举所有输入组合。

选择凭据模式共同携带 `credential_source=vault`、`vault_credential_id`、`vault_type_key`；下面“引用动态字段”省略这些共同元数据。候选 ID、版本与 actor context 由服务端管理；表中均不记录真实凭据值。

| 序号 | 入口 | 手动请求字段 | 引用类型 / 动态字段 | 回放与额外发现 |
|---|---|---|---|---|
| 001 | K8S `k8s_cluster` | — | 不接入本次凭据池 | 静态核对现有专用路径 |
| 002 | Docker `docker` | `username`、`password`、`port` | `host/ssh`；`port` | 两模式通过 |
| 003 | vCenter `vmware_vc` | `username`、`port`、`ssl`、`password` | `cloud/platform_api`；`port`、`ssl` | 两模式通过 |
| 004 | ZStack `zstack` | `username`、`port`、`verify_tls`、`password` | `cloud/platform_api`；`port`、`verify_tls` | 两模式通过；采集体未实现 |
| 005 | 华三 UIS `h3c_cas` | `username`、`port`、`verify_tls`、`password` | `cloud/platform_api`；`port`、`verify_tls` | 两模式通过 |
| 006 | 云宏 WinSphere `winsphere` | `user`、`password`、`https_port`、`verify_tls` | `cloud/platform_api`；`https_port`、`verify_tls` | 两模式通过 |
| 007 | OpenStack `openstack` | `username`、`port`、`verify_tls`、`user_domain_name`、`project_id`、`password` | `cloud/openstack`；`port`、`verify_tls`、`project_id` | 两模式通过；连接选项缺口见上表 |
| 008 | SmartX `smartx` | `username`、`port`、`verify_tls`、`source`、`password` | `cloud/platform_api`；`port`、`verify_tls`、`source` | 两模式通过；连接选项缺口见上表 |
| 009 | ManageOne `manageone` | `username`、`port`、`verify_tls`、`password` | `cloud/platform_api`；`port`、`verify_tls` | 两模式通过；连接选项缺口见上表 |
| 010 | FusionCompute `fusioncompute` | `username`、`port`、`verify_tls`、`user_type`、`password` | `cloud/platform_api`；`port`、`verify_tls`、`user_type` | 两模式通过；连接选项缺口见上表 |
| 011 | 深信服 HCI `sangforhci` | `username`、`port`、`verify_tls`、`password` | `cloud/platform_api`；`port`、`verify_tls` | 两模式通过 |
| 012 | 深信服 SCP `sangforscp` | `username`、`port`、`verify_tls`、`password` | `cloud/platform_api`；`port`、`verify_tls` | 两模式通过 |
| 013 | Nutanix HCI `nutanixhci` | `username`、`port`、`verify_tls`、`password` | `cloud/platform_api`；`port`、`verify_tls` | 两模式通过；连接选项缺口见上表 |
| 014 | 浪潮 InCloud Rail `inspurincloudrail` | `username`、`port`、`verify_tls`、`password` | `cloud/platform_api`；`port`、`verify_tls` | 两模式通过；连接选项缺口见上表 |
| 015 | NetWork `network` | `version`、`snmp_port`、`level`、`username`、`integrity`、`authkey`、`privacy`、`privkey` | `network/snmp`；`snmp_port` | 两模式通过 |
| 016 | 网络设备配置文件 `network_config_file` | `username`、`password`、`enable_password`、`port`、`transport_protocol` | `network/ssh`；`enable_password`、`port`、`transport_protocol` | 两模式通过 |
| 017 | 安全设备 `security_device` | `version`、`snmp_port`、`level`、`username`、`integrity`、`authkey`、`privacy`、`privkey` | `network/snmp`；`snmp_port` | 两模式通过 |
| 018 | IP 发现 `ip_discovery` | — | 不接入本次凭据池 | 静态核对现有专用路径 |
| 019 | Mysql `mysql` | `user`、`password`、`port` | `database/sql`；`port` | 两模式通过 |
| 020 | 【BETA】InfluxDB `influxdb` | `scheme`、`port`、`verify_tls`、`token` | `database/token`；`scheme`、`port`、`verify_tls` | 两模式通过 |
| 021 | PostgreSQL `postgresql` | `user`、`password`、`port` | `database/sql`；`port` | 两模式通过 |
| 022 | 【BETA】MSSQL `mssql` | `user`、`password`、`port`、`database` | `database/sql`；`port`、`database` | 两模式通过 |
| 023 | Redis `redis` | `username`、`password`、`port` | `database/ssh`；`port` | 两模式通过 |
| 024 | 【BETA】MongoDB `mongodb` | `username`、`password`、`port` | `database/ssh`；`port` | 两模式通过 |
| 025 | 【BETA】Elasticsearch `es` | `username`、`password`、`port` | `database/ssh`；`port` | 两模式通过 |
| 026 | 【BETA】HBase `hbase` | `username`、`password`、`port` | `database/ssh`；`port` | 两模式通过 |
| 027 | OceanBase `oceanbase` | `user`、`password`、`port` | `database/sql`；`port` | 两模式通过 |
| 028 | 瀚高HighGo `highgo` | `user`、`password`、`port` | `database/sql`；`port` | 两模式通过 |
| 029 | Informix `informix` | `username`、`password`、`port` | `database/ssh`；`port` | 两模式通过 |
| 030 | Sybase `sybase` | `username`、`password`、`port` | `database/ssh`；`port` | 两模式通过 |
| 031 | Couchbase `couchbase` | `user`、`password`、`port`、`bucket` | `database/sql`；`port`、`bucket` | 两模式通过；采集体未实现 |
| 032 | MyCAT `mycat` | `username`、`password`、`port` | `database/ssh`；`port` | 两模式通过 |
| 033 | SAP HANA `sap_hana` | `user`、`password`、`port` | `database/sql`；`port` | 两模式通过；采集体未实现 |
| 034 | InterSystems IRIS `iris` | `user`、`password`、`port`、`namespace` | `database/sql`；`port`、`namespace` | 两模式通过；采集体未实现 |
| 035 | Redis Sentinel `redis_sentinel` | `username`、`password`、`port` | `database/ssh`；`port` | 两模式通过 |
| 036 | GBase 8s `gbase8s` | `username`、`password`、`port` | `database/ssh`；`port` | 两模式通过 |
| 037 | 神通 Oscar `oscar` | `username`、`password`、`port` | `database/ssh`；`port` | 两模式通过 |
| 038 | TongRDS `tongrds` | `user`、`password`、`port` | `database/sql`；`port` | 两模式通过；采集体未实现 |
| 039 | TDSQL `tdsql` | `user`、`password`、`port` | `database/sql`；`port` | 两模式通过 |
| 040 | 达梦数据库 `dameng` | `username`、`password`、`port` | `database/ssh`；`port` | 两模式通过 |
| 041 | DB2 `db2` | `username`、`password`、`port` | `database/ssh`；`port` | 两模式通过 |
| 042 | TiDB `tidb` | `username`、`password`、`port` | `database/ssh`；`port` | 两模式通过 |
| 043 | GBase 8a `gbase8a` | `user`、`password`、`port` | `database/sql`；`port` | 两模式通过 |
| 044 | Greenplum `greenplum` | `user`、`password`、`port` | `database/sql`；`port` | 两模式通过 |
| 045 | 人大金仓 `kingbase` | `user`、`password`、`port` | `database/sql`；`port` | 两模式通过 |
| 046 | openGauss `opengauss` | `user`、`password`、`port` | `database/sql`；`port` | 两模式通过 |
| 047 | Vastbase `vastbase` | `user`、`password`、`port` | `database/sql`；`port` | 两模式通过 |
| 048 | 【BETA】华为存储 `storage` | `username`、`port`、`verify_tls`、`password` | `storage/platform_api`；`port`、`verify_tls` | 两模式通过 |
| 049 | 【BETA】Dell Unity `dell_unity` | `username`、`port`、`verify_tls`、`password` | `storage/platform_api`；`port`、`verify_tls` | 两模式通过 |
| 050 | 【BETA】NetApp ONTAP `netapp_ontap` | `username`、`port`、`verify_tls`、`password` | `storage/platform_api`；`port`、`verify_tls` | 两模式通过 |
| 051 | IBM Storwize `ibm_storwize` | `username`、`port`、`verify_tls`、`password` | `storage/platform_api`；`port`、`verify_tls` | 两模式通过；采集体未实现 |
| 052 | IBM DS `ibm_ds` | `regions`、`accessKey`、`accessSecret` | `storage/cloud`；`regions` | 两模式通过；采集体未实现 |
| 053 | EMC Symmetrix `emc_symmetrix` | `username`、`port`、`verify_tls`、`password` | `storage/platform_api`；`port`、`verify_tls` | 两模式通过；采集体未实现 |
| 054 | 【BETA】Hitachi VSP `hds_vsp` | `username`、`port`、`verify_tls`、`password` | `storage/platform_api`；`port`、`verify_tls` | 两模式通过 |
| 055 | 宏杉存储 `macrosan` | `version`、`snmp_port`、`level`、`username`、`integrity`、`authkey`、`privacy`、`privkey` | `storage/snmp`；`snmp_port` | 两模式通过 |
| 056 | 【BETA】Pure Storage `pure_array` | `username`、`port`、`verify_tls`、`password` | `storage/platform_api`；`port`、`verify_tls` | 两模式通过 |
| 057 | NetApp Cluster `netapp_cluster` | `username`、`port`、`verify_tls`、`password` | `storage/platform_api`；`port`、`verify_tls` | 两模式通过 |
| 058 | Oracle ZFS `oraclezfs` | `username`、`port`、`verify_tls`、`password` | `storage/platform_api`；`port`、`verify_tls` | 两模式通过；采集体未实现 |
| 059 | Infinidat `infinidat` | `username`、`port`、`verify_tls`、`password` | `storage/platform_api`；`port`、`verify_tls` | 两模式通过；采集体未实现 |
| 060 | 磁带库 `tape_library` | `version`、`snmp_port`、`level`、`username`、`integrity`、`authkey`、`privacy`、`privkey` | `storage/snmp`；`snmp_port` | 两模式通过 |
| 061 | XSKY `xsky` | `regions`、`accessKey`、`accessSecret` | `storage/cloud`；`regions` | 两模式通过；采集体未实现 |
| 062 | 【BETA】Dell PowerStore `dell_powerstore` | `username`、`port`、`verify_tls`、`password` | `storage/platform_api`；`port`、`verify_tls` | 两模式通过 |
| 063 | 【BETA】HPE 3PAR/Primera `hp_3par` | `username`、`port`、`verify_tls`、`password` | `storage/platform_api`；`port`、`verify_tls` | 两模式通过 |
| 064 | 阿里云 `aliyun_account` | `regions`、`accessKey`、`accessSecret` | `cloud/cloud`；`regions` | 两模式通过 |
| 065 | 腾讯云 `qcloud` | `regions`、`accessKey`、`accessSecret` | `cloud/cloud`；`regions` | 两模式通过 |
| 066 | 华为云【beta】 `hwcloud` | `regions`、`accessKey`、`accessSecret`、`project_id` | `cloud/cloud`；`regions`、`project_id` | 两模式通过 |
| 067 | FusionInsight【beta】 `fusioninsight` | `username`、`port`、`verify_tls`、`password` | `cloud/platform_api`；`port`、`verify_tls` | 两模式通过 |
| 068 | AWS `aws` | `regions`、`accessKey`、`accessSecret` | `cloud/cloud`；`regions` | 两模式通过 |
| 069 | Azure `azure` | `username`、`port`、`verify_tls`、`tenant_id`、`subscription_id`、`password` | `cloud/oauth_client`；`port`、`verify_tls`、`subscription_id` | 两模式通过；连接选项缺口见上表 |
| 070 | 主机 `host` | `username`、`password`、`port` | `host/ssh`；`port` | 两模式通过 |
| 071 | 配置文件 `config_file` | `username`、`password`、`port` | `host/ssh`；`port` | 两模式通过 |
| 072 | 物理服务器 SSH `physcial_server` | `username`、`password`、`port` | `host/ssh`；`port` | 两模式通过 |
| 073 | 【BETA】物理服务器 IPMI `physcial_server_ipmi` | `username`、`password`、`port`、`privilege` | `host/ipmi`；`port`、`privilege` | 两模式通过 |
| 074 | 【BETA】物理服务器 Redfish `physcial_server_redfish` | `username`、`port`、`verify_tls`、`password` | `host/redfish`；`port`、`verify_tls` | 两模式通过 |
| 075 | HMC `hmc` | `username`、`password`、`port` | `host/ssh`；`port` | 两模式通过 |
| 076 | PC发现 `pc` | `username`、`port`、`password` | `host/winrm`；`port`、`scheme` | 两模式通过 |
| 077 | Nginx `nginx` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 078 | 【BETA】MinIO `minio` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 079 | Zookeeper `zookeeper` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 080 | Kafka `kafka` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 081 | Consul `consul` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 082 | Etcd `etcd` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 083 | RabbitMQ `rabbitmq` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 084 | Tomcat `tomcat` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 085 | Apache `apache` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 086 | ActiveMQ `activemq` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 087 | IIS `iis` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 088 | Tuxedo `tuxedo` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 089 | Memcached `memcached` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 090 | RocketMQ `rocketmq` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 091 | OpenResty `openresty` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 092 | Squid `squid` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 093 | HAProxy `haproxy` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 094 | KeepAlive【beta】 `keepalive` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 095 | Spark `spark` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 096 | Nacos `nacos` | `username`、`port`、`verify_tls`、`scheme`、`password` | `middleware/sql`；`port`、`verify_tls`、`scheme` | 两模式通过 |
| 097 | IBM MQ `ibmmq` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 098 | TongLINK/Q `tonglinkq` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 099 | TongGTP `tonggtp` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 100 | IBM HTTP Server `ihs` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 101 | IBM CICS `cics` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 102 | HDFS `hdfs` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 103 | YARN `yarn` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 104 | Storm `storm` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 105 | Ambari `ambari` | `username`、`port`、`verify_tls`、`password` | `middleware/sql`；`port`、`verify_tls` | 两模式通过；采集体未实现 |
| 106 | BES `bes` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 107 | Apusic `apusic` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 108 | InforSuite AS `inforsuite_as` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 109 | Ceph `ceph` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 110 | JBoss `jboss` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 111 | Jetty `jetty` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 112 | TongWeb `tongweb` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 113 | WebLogic `weblogic` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 114 | WebSphere `websphere` | `username`、`password`、`port` | `middleware/ssh`；`port` | 两模式通过 |
| 115 | SSL证书 `ssl_cer` | — | 不接入本次凭据池 | 静态核对；SSL 专项回归通过 |

## 复验

仓库根目录启动，要求已安装 web/server 依赖且企业子模块可用。导出的输入仅为目录元数据和合成测试凭据，不使用用户真实凭据：

```sh
export DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true
export CMDB_PAGE_TREE=/tmp/cmdb-current-tree.json
export CMDB_PAGE_PAYLOADS=/tmp/cmdb-page-payloads.json
(cd server && uv run --no-sync python -m apps.cmdb.tests.e2e.export_collection_page_tree "$CMDB_PAGE_TREE")
(cd web && pnpm exec vitest run 'src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/__tests__/credentialPagePayloads.test.tsx')
(cd server && uv run --no-sync pytest apps/cmdb/tests/e2e/test_credential_page_payloads.py --no-cov --nomigrations -o addopts='')
```

本机 Node 默认版本较旧，实际执行使用 Codex 的 Node 24。前端脚本通过 `node --import tsx` 运行，避免 tsx CLI 的 IPC 限制。

验证结果：

- 当前页面回放：112 项前端测试，生成 224 组请求；224 组后端集成回放通过。
- 前端采集页面测试目录：15 个文件、473 条通过；平台凭据脚本通过。
- 后端凭据、序列化、下发、SSL、系统内置 schema 及企业引用相关测试：1,402 条通过。
- 历史双字段加密与脱敏额外回归：18 条通过；补跑云下发测试 9 条通过，另 3 条因测试假定 OpenStack/ManageOne/SmartX 未注册而失败，当前企业插件已注册，属于旧测试环境假设失效（单独执行亦相同）。
- `pnpm type-check` 通过；本次修改文件的 ESLint 通过。全量 `pnpm lint` 有 31 个错误、90 个警告，错误位于未修改的 APM/日志/监控/系统管理等文件；未修改这些无关文件。
- SQLite 测试使用 `--nomigrations`：默认迁移路径有既存 `NewSessionEventRelation has no field named 'event'` 问题。另有旧企业目录测试固定期望不包含 SSL、包含 server_bmc，已知与当前目录不一致；本次不将旧目录快照作为当前事实，也未批量重写它。

本次未部署服务、未修改真实任务或现有凭据，未做设备实测。修复涉及主仓库与 enterprise 子模块，两边需一并交付。
