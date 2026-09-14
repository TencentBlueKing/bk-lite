# 创建采集任务后的立即执行插件清单

2026-09-11 当前社区版及已加载企业版对象树的运行时快照。来源为
`get_collect_obj_tree()` 与 `NodeParamsFactory` 实际注册结果，不是额外准入白名单。

- 开关 `CMDB_FIRST_COLLECTION_ENABLED` 开启、周期调度启用、周期至少 15 分钟时，普通任务创建后触发一次。
- Network 设备与拓扑按各自周期判断；拓扑必须启用，未填拓扑周期沿用设备周期 5 倍。
- 排除 K8S、主机配置文件和网络配置文件；系统 NodeMgmt 自动同步的隐藏区域主机任务不经过此首采入口。
- 接入节点需满足既有 Linux、组织授权、Telegraf 与 Executor 运行条件。
- “立即执行”指 one-shot 触发 Stargazer，接受请求不等于完成采集或资产入库。

当前共有 **118 个可选入口（116 个不同 model_id）**，其中 **115 个入口（113 个不同 model_id）**
满足首采类型条件。物理服务器 SSH、IPMI、Redfish 是三个入口，IPMI/Redfish 共用 protocol 适配。
115 个入口均已用合成参数验证子配置生成与 one-shot 转换成功；不表示真实目标采集已全部实测。

| 分类 | 采集对象 | model_id | 驱动 | 下发 plugin_name | 创建后首采 |
|---|---|---|---|---|---|
| 容器 | K8S | `k8s_cluster` | protocol | `—` | 不触发 |
| 容器 | Docker | `docker` | job | `docker_info` | 达到周期阈值时触发 |
| 虚拟化/私有云 | vCenter | `vmware_vc` | protocol | `vmware_info` | 达到周期阈值时触发 |
| 虚拟化/私有云 | ZStack | `zstack` | protocol | `zstack_info` | 达到周期阈值时触发 |
| 虚拟化/私有云 | 华三 UIS | `h3c_cas` | protocol | `h3c_cas_info` | 达到周期阈值时触发 |
| 虚拟化/私有云 | 云宏 WinSphere | `winsphere` | protocol | `winsphere_info` | 达到周期阈值时触发 |
| 虚拟化/私有云 | OpenStack | `openstack` | protocol | `openstack_info` | 达到周期阈值时触发 |
| 虚拟化/私有云 | SmartX | `smartx` | protocol | `smartx_info` | 达到周期阈值时触发 |
| 虚拟化/私有云 | ManageOne | `manageone` | protocol | `manageone_info` | 达到周期阈值时触发 |
| 虚拟化/私有云 | FusionCompute | `fusioncompute` | protocol | `fusioncompute_info` | 达到周期阈值时触发 |
| 虚拟化/私有云 | 深信服 HCI | `sangforhci` | protocol | `sangforhci_info` | 达到周期阈值时触发 |
| 虚拟化/私有云 | 深信服 SCP | `sangforscp` | protocol | `sangforscp_info` | 达到周期阈值时触发 |
| 虚拟化/私有云 | Nutanix HCI | `nutanixhci` | protocol | `nutanixhci_info` | 达到周期阈值时触发 |
| 虚拟化/私有云 | 浪潮 InCloud Rail | `inspurincloudrail` | protocol | `inspurincloudrail_info` | 达到周期阈值时触发 |
| 网络 | NetWork | `network` | protocol | `snmp_facts` | 按设备、拓扑各自周期触发 |
| 网络 | 网络设备配置文件 | `network_config_file` | protocol | `—` | 不触发 |
| 网络 | Brocade FC | `brocade_fc` | job | `brocade_fc_info` | 达到周期阈值时触发 |
| 网络 | Cisco FC | `cisco_fc` | job | `cisco_fc_info` | 达到周期阈值时触发 |
| 网络 | F5 | `f5` | protocol | `f5_info` | 达到周期阈值时触发 |
| 网络 | 安全设备 | `security_device` | protocol | `security_device_info` | 达到周期阈值时触发 |
| IPAM | IP 发现 | `ip` | protocol | `ip_discovery` | 达到周期阈值时触发 |
| 数据库 | Mysql | `mysql` | protocol | `mysql_info` | 达到周期阈值时触发 |
| 数据库 | 【BETA】InfluxDB | `influxdb` | protocol | `influxdb_info` | 达到周期阈值时触发 |
| 数据库 | PostgreSQL | `postgresql` | protocol | `postgresql_info` | 达到周期阈值时触发 |
| 数据库 | 【BETA】MSSQL | `mssql` | protocol | `mssql_info` | 达到周期阈值时触发 |
| 数据库 | Redis | `redis` | job | `redis_info` | 达到周期阈值时触发 |
| 数据库 | 【BETA】MongoDB | `mongodb` | job | `mongodb_info` | 达到周期阈值时触发 |
| 数据库 | 【BETA】Elasticsearch | `es` | job | `es_info` | 达到周期阈值时触发 |
| 数据库 | 【BETA】HBase | `hbase` | job | `hbase_info` | 达到周期阈值时触发 |
| 数据库 | OceanBase | `oceanbase` | protocol | `oceanbase_info` | 达到周期阈值时触发 |
| 数据库 | 瀚高HighGo | `highgo` | protocol | `highgo_info` | 达到周期阈值时触发 |
| 数据库 | Informix | `informix` | job | `informix_info` | 达到周期阈值时触发 |
| 数据库 | Sybase | `sybase` | job | `sybase_info` | 达到周期阈值时触发 |
| 数据库 | Couchbase | `couchbase` | protocol | `couchbase_info` | 达到周期阈值时触发 |
| 数据库 | MyCAT | `mycat` | job | `mycat_info` | 达到周期阈值时触发 |
| 数据库 | SAP HANA | `sap_hana` | protocol | `sap_hana_info` | 达到周期阈值时触发 |
| 数据库 | InterSystems IRIS | `iris` | protocol | `iris_info` | 达到周期阈值时触发 |
| 数据库 | Redis Sentinel | `redis_sentinel` | job | `redis_sentinel_info` | 达到周期阈值时触发 |
| 数据库 | GBase 8s | `gbase8s` | job | `gbase8s_info` | 达到周期阈值时触发 |
| 数据库 | 神通 Oscar | `oscar` | job | `oscar_info` | 达到周期阈值时触发 |
| 数据库 | TongRDS | `tongrds` | protocol | `tongrds_info` | 达到周期阈值时触发 |
| 数据库 | TDSQL | `tdsql` | protocol | `tdsql_info` | 达到周期阈值时触发 |
| 数据库 | 达梦数据库 | `dameng` | job | `dameng_info` | 达到周期阈值时触发 |
| 数据库 | DB2 | `db2` | job | `db2_info` | 达到周期阈值时触发 |
| 数据库 | TiDB | `tidb` | job | `tidb_info` | 达到周期阈值时触发 |
| 数据库 | GBase 8a | `gbase8a` | protocol | `gbase8a_info` | 达到周期阈值时触发 |
| 数据库 | Greenplum | `greenplum` | protocol | `greenplum_info` | 达到周期阈值时触发 |
| 数据库 | 人大金仓 | `kingbase` | protocol | `kingbase_info` | 达到周期阈值时触发 |
| 数据库 | openGauss | `opengauss` | protocol | `opengauss_info` | 达到周期阈值时触发 |
| 数据库 | Vastbase | `vastbase` | protocol | `vastbase_info` | 达到周期阈值时触发 |
| 存储 | 【BETA】华为存储 | `storage` | protocol | `oceanstor_info` | 达到周期阈值时触发 |
| 存储 | 【BETA】Dell Unity | `dell_unity` | protocol | `dell_unity_info` | 达到周期阈值时触发 |
| 存储 | 【BETA】NetApp ONTAP | `netapp_ontap` | protocol | `netapp_ontap_info` | 达到周期阈值时触发 |
| 存储 | IBM Storwize | `ibm_storwize` | protocol | `ibm_storwize_info` | 达到周期阈值时触发 |
| 存储 | IBM DS | `ibm_ds` | protocol | `ibm_ds_info` | 达到周期阈值时触发 |
| 存储 | EMC Symmetrix | `emc_symmetrix` | protocol | `emc_symmetrix_info` | 达到周期阈值时触发 |
| 存储 | 【BETA】Hitachi VSP | `hds_vsp` | protocol | `hds_vsp_info` | 达到周期阈值时触发 |
| 存储 | 宏杉存储 | `macrosan` | protocol | `macrosan_info` | 达到周期阈值时触发 |
| 存储 | 【BETA】Pure Storage | `pure_array` | protocol | `pure_array_info` | 达到周期阈值时触发 |
| 存储 | NetApp Cluster | `netapp_cluster` | protocol | `netapp_cluster_info` | 达到周期阈值时触发 |
| 存储 | Oracle ZFS | `oraclezfs` | protocol | `oraclezfs_info` | 达到周期阈值时触发 |
| 存储 | Infinidat | `infinidat` | protocol | `infinidat_info` | 达到周期阈值时触发 |
| 存储 | 磁带库 | `tape_library` | protocol | `tape_library_info` | 达到周期阈值时触发 |
| 存储 | XSKY | `xsky` | protocol | `xsky_info` | 达到周期阈值时触发 |
| 存储 | 【BETA】Dell PowerStore | `dell_powerstore` | protocol | `dell_powerstore_info` | 达到周期阈值时触发 |
| 存储 | 【BETA】HPE 3PAR/Primera | `hp_3par` | protocol | `hp_3par_info` | 达到周期阈值时触发 |
| 云平台 | 阿里云 | `aliyun_account` | protocol | `aliyun_info` | 达到周期阈值时触发 |
| 云平台 | 腾讯云 | `qcloud` | protocol | `qcloud_info` | 达到周期阈值时触发 |
| 云平台 | 华为云【beta】 | `hwcloud` | protocol | `huaweicloud_info` | 达到周期阈值时触发 |
| 云平台 | FusionInsight【beta】 | `fusioninsight` | protocol | `fusioninsight_info` | 达到周期阈值时触发 |
| 云平台 | AWS | `aws` | protocol | `aws_info` | 达到周期阈值时触发 |
| 云平台 | Azure | `azure` | protocol | `azure_info` | 达到周期阈值时触发 |
| 主机 | 主机 | `host` | job | `host_info` | 达到周期阈值时触发 |
| 主机 | 配置文件 | `config_file` | job | `—` | 不触发 |
| 主机 | 物理服务器 SSH | `physcial_server` | job | `_info` | 达到周期阈值时触发 |
| 主机 | 【BETA】物理服务器 IPMI | `physcial_server` | protocol | `physcial_server_info` | 达到周期阈值时触发 |
| 主机 | 【BETA】物理服务器 Redfish | `physcial_server` | protocol | `physcial_server_info` | 达到周期阈值时触发 |
| 主机 | 服务器BMC | `server_bmc` | protocol | `server_bmc_info` | 达到周期阈值时触发 |
| 主机 | HMC | `hmc` | job | `hmc_info` | 达到周期阈值时触发 |
| 主机 | PC发现 | `pc` | job | `pc_info` | 达到周期阈值时触发 |
| 中间件 | Nginx | `nginx` | job | `nginx_info` | 达到周期阈值时触发 |
| 中间件 | 【BETA】MinIO | `minio` | job | `minio_info` | 达到周期阈值时触发 |
| 中间件 | Zookeeper | `zookeeper` | job | `zookeeper_info` | 达到周期阈值时触发 |
| 中间件 | Kafka | `kafka` | job | `kafka_info` | 达到周期阈值时触发 |
| 中间件 | Consul | `consul` | job | `consul_info` | 达到周期阈值时触发 |
| 中间件 | Etcd | `etcd` | job | `etcd_info` | 达到周期阈值时触发 |
| 中间件 | RabbitMQ | `rabbitmq` | job | `rabbitmq_info` | 达到周期阈值时触发 |
| 中间件 | Tomcat | `tomcat` | job | `tomcat_info` | 达到周期阈值时触发 |
| 中间件 | Apache | `apache` | job | `apache_info` | 达到周期阈值时触发 |
| 中间件 | ActiveMQ | `activemq` | job | `activemq_info` | 达到周期阈值时触发 |
| 中间件 | IIS | `iis` | job | `iis_info` | 达到周期阈值时触发 |
| 中间件 | Tuxedo | `tuxedo` | job | `tuxedo_info` | 达到周期阈值时触发 |
| 中间件 | Memcached | `memcached` | job | `memcached_info` | 达到周期阈值时触发 |
| 中间件 | RocketMQ | `rocketmq` | job | `rocketmq_info` | 达到周期阈值时触发 |
| 中间件 | OpenResty | `openresty` | job | `openresty_info` | 达到周期阈值时触发 |
| 中间件 | Squid | `squid` | job | `squid_info` | 达到周期阈值时触发 |
| 中间件 | HAProxy | `haproxy` | job | `haproxy_info` | 达到周期阈值时触发 |
| 中间件 | KeepAlive【beta】 | `keepalive` | job | `keepalived_info` | 达到周期阈值时触发 |
| 中间件 | Spark | `spark` | job | `spark_info` | 达到周期阈值时触发 |
| 中间件 | Nacos | `nacos` | protocol | `nacos_info` | 达到周期阈值时触发 |
| 中间件 | IBM MQ | `ibmmq` | job | `ibmmq_info` | 达到周期阈值时触发 |
| 中间件 | TongLINK/Q | `tonglinkq` | job | `tonglinkq_info` | 达到周期阈值时触发 |
| 中间件 | TongGTP | `tonggtp` | job | `tonggtp_info` | 达到周期阈值时触发 |
| 中间件 | IBM HTTP Server | `ihs` | job | `ihs_info` | 达到周期阈值时触发 |
| 中间件 | IBM CICS | `cics` | job | `cics_info` | 达到周期阈值时触发 |
| 中间件 | HDFS | `hdfs` | job | `hdfs_info` | 达到周期阈值时触发 |
| 中间件 | YARN | `yarn` | job | `yarn_info` | 达到周期阈值时触发 |
| 中间件 | Storm | `storm` | job | `storm_info` | 达到周期阈值时触发 |
| 中间件 | Ambari | `ambari` | protocol | `ambari_info` | 达到周期阈值时触发 |
| 中间件 | BES | `bes` | job | `bes_info` | 达到周期阈值时触发 |
| 中间件 | Apusic | `apusic` | job | `apusic_info` | 达到周期阈值时触发 |
| 中间件 | InforSuite AS | `inforsuite_as` | job | `inforsuite_as_info` | 达到周期阈值时触发 |
| 中间件 | Ceph | `ceph` | job | `ceph_info` | 达到周期阈值时触发 |
| 中间件 | JBoss | `jboss` | job | `jboss_info` | 达到周期阈值时触发 |
| 中间件 | Jetty | `jetty` | job | `jetty_info` | 达到周期阈值时触发 |
| 中间件 | TongWeb | `tongweb` | job | `tongweb_info` | 达到周期阈值时触发 |
| 中间件 | WebLogic | `weblogic` | job | `weblogic_info` | 达到周期阈值时触发 |
| 中间件 | WebSphere | `websphere` | job | `websphere_info` | 达到周期阈值时触发 |

## 独立拓扑通道与已有任务适配

| model_id | 下发 plugin_name | 说明 |
|---|---|---|
| `network_topo` | `snmp_topo` | Network 开启的独立拓扑通道，不计为对象树的独立入口 |
| `oracle` | `oracle_info` | 当前未出现在可选对象树，后端仍有适配；已有任务按普通首采策略处理 |
| `aix` | `aix_info` | 当前归入主机入口，后端保留适配；已有任务按普通首采策略处理 |
| `hpux` | `hpux_info` | 当前归入主机入口，后端保留适配；已有任务按普通首采策略处理 |
| `domestic_linux` | `domestic_linux_info` | 当前归入主机入口，后端保留适配；已有任务按普通首采策略处理 |

物理服务器 SSH 下发的 `plugin_name` 实际继承为 `_info`，表中如实记录。
Stargazer 当前以 `model_id=physcial_server` 和 `executor_type=job` 解析插件，
不因这个元数据值而判定本链路中断；本次没有修改这项既有行为。

上述快照会随企业扩展加载情况变化。长期触发规则以 [首采规格](./spec.md) 和当前代码为准。
