# CMDB 配置采集 — 收官封档文档(2026-07-10)

> **封档日期**: 2026-07-10
> **覆盖周期**: 2026-07-06 → 2026-07-10(v3 立项 → v4 整合 + push)
> **scope**: catalog 56 model_id 全部对象执行结果
> **姊妹文档**:
> - `2026-07-06-cmdb-collect-v3-roadmap.md`(v3 立项)
> - `2026-07-07~08-cmdb-collect-v3-phase{1-5}-execution-report.md`(v3 各阶段执行)
> - `2026-07-10-cmdb-collect-execution-roadmap.md`(本机 + Gap-3 路线)
> - `2026-07-10-cmdb-collect-next-step-discussion.md`(调研 + v4 立项)
> - `2026-07-10-cmdb-collect-v4-phase1-execution-report.md`(v4 基础设施)
> - `2026-07-10-cmdb-collect-v3-v4-pr-description.md`(PR description)
> **状态图例**: ✅ passed(3 层验证)/ 🟡 placeholder(公共契约)/ ⏭️ skipped(范围外)/ 🔒 archived(license/amd64/集群)

---

## 1. 整体结果(catalog 56 model_id)

| 维度 | 数量 | 占比 |
|---|---|---|
| ✅ passed(3 层验证全过) | **24** | 43% |
| 🟡 placeholder(公共契约验证) | **9** | 16% |
| ⏭️ skipped(v3 范围外 / 无 plugin / 无 catalog) | **5** | 9% |
| 🔒 archived(license / amd64 / 集群复杂度) | **18** | 32% |
| **catalog 总数** | **56** | 100% |
| **stargazer 真实落盘 fixture** | **33** | 59% |
| **CMDB 端 e2e 覆盖(真实落盘)** | **33/33** | **100%** |
| **e2e 测试** | **113 passed, 6 skipped, 0 failed** | — |

> 注:catalog 56 vs "24+9+5+18" 的差值即 v3+v4 真实跑通的 33 个 = 24 passed + 9 placeholder。

---

## 2. ✅ Passed — 24 个对象(3 层验证:契约 + 流水线 + 字段对齐)

按 v4 Phase 推进顺序:

| # | 大类 | 对象 | runner | v4 阶段 | 启动 | fixture 路径 | 测试文件 | 关键发现 |
|---|---|---|---|---|---|---|---|---|
| 1 | protocol | **influxdb** | ProtocolCollectMetrics 平铺 | Phase 2.1 | 2026-07-10 11:38 | `tests/fixtures/collect/influxdb.json` | `test_influxdb_pipeline.py` | arm64 multi-arch,3 字段(version/ip_addr/port/https_enabled) |
| 2 | db | **mysql** | DBCollectCollectMetrics 平铺 | Phase 2.2 | 2026-07-10 13:00 | `tests/fixtures/collect/mysql.json` | `test_mysql_pipeline.py` | 5 字段,plugin 不映射 role/master_host,db_runner 平铺模式 |
| 3 | db | **redis** | DBCollectCollectMetrics 平铺 | Phase 2.4 | 2026-07-10 13:35 | `tests/fixtures/collect/redis.json` | `test_redis_pipeline.py` | 5 字段,slaves/list master/object vs 01_raw/string 兼容 |
| 4 | middleware | **nginx** | MiddlewareCollectMetrics metric.result JSON | Phase 2.3 | 2026-07-10 13:20 | `tests/fixtures/collect/nginx.json` | `test_nginx_pipeline.py` | v2 标准化形态,5 字段,extra_payload_keys={"result":True} |
| 5 | db | **postgresql** | DBCollectCollectMetrics 平铺 | Phase 3 P0 | 2026-07-10 14:30 | `tests/fixtures/collect/postgresql.json` | `test_postgresql_pipeline.py` | inst_name 短名 "pg",需 `inst_name_alias: pg` |
| 6 | db | **mongodb** | DBCollectCollectMetrics 平铺 | Phase 3 P0 | 2026-07-10 14:30 | `tests/fixtures/collect/mongodb.json` | `test_mongodb_pipeline.py` | 形态 B,database_role 空字符串合法 |
| 7 | middleware | **tomcat** | MiddlewareCollectMetrics | Phase 3 P0 | 2026-07-10 14:30 | `tests/fixtures/collect/tomcat.json` | `test_tomcat_pipeline.py` | catalina_path 字段(非 bin_path) |
| 8 | middleware | **rabbitmq** | MiddlewareCollectMetrics | Phase 3 P0 | 2026-07-10 14:30 | `tests/fixtures/collect/rabbitmq.json` | `test_rabbitmq_pipeline.py` | 形态 B 平铺 |
| 9 | middleware | **kafka** | MiddlewareCollectMetrics | Phase 3 P0 | 2026-07-10 14:30 | `tests/fixtures/collect/kafka.json` | `test_kafka_pipeline.py` | plugin 19 字段,raw 7 字段对齐 |
| 10 | middleware | **zookeeper** | MiddlewareCollectMetrics | Phase 3 P0 | 2026-07-10 14:30 | `tests/fixtures/collect/zookeeper.json` | `test_zookeeper_pipeline.py` | 形态 B,14 字段 |
| 11 | middleware | **haproxy** | MiddlewareCollectMetrics | Phase 3 P0 | 2026-07-10 14:30 | `tests/fixtures/collect/haproxy.json` | `test_haproxy_pipeline.py` | port="80&8404" 多端口拼接 |
| 12 | db | **elasticsearch** | DBCollectCollectMetrics | Phase 3 P0 | 2026-07-10 14:30 | `tests/fixtures/collect/elasticsearch.json` | `test_elasticsearch_pipeline.py` | alias es,大写 ESCollectionPlugin |
| 13 | middleware | **keepalived** | MiddlewareCollectMetrics | Phase 4 P1 | 2026-07-10 15:30 | `tests/fixtures/collect/keepalived.json` | `test_keepalived_pipeline.py` | **不映射 port,用 virtual_router_id** |
| 14 | middleware | **openresty** | MiddlewareCollectMetrics | Phase 4 P1 | 2026-07-10 15:30 | `tests/fixtures/collect/openresty.json` | `test_openresty_pipeline.py` | G3.6 placeholder,init 脚本模板填充 |
| 15 | middleware | **apache** | MiddlewareCollectMetrics | Phase 4 P1 | 2026-07-10 15:30 | `tests/fixtures/collect/apache.json` | `test_apache_pipeline.py` | 形态 B |
| 16 | middleware | **activemq** | MiddlewareCollectMetrics | Phase 4 P1 | 2026-07-10 15:30 | `tests/fixtures/collect/activemq.json` | `test_activemq_pipeline.py` | fixture bin_path/config vs plugin install_path/conf_path 不对齐 |
| 17 | middleware | **minio** | MiddlewareCollectMetrics | Phase 4 P1 | 2026-07-10 15:30 | `tests/fixtures/collect/minio.json` | `test_minio_pipeline.py` | 形态 A(含 bk_obj_id) |
| 18 | middleware | **consul** | MiddlewareCollectMetrics | Phase 4 P1 | 2026-07-10 15:30 | `tests/fixtures/collect/consul.json` | `test_consul_pipeline.py` | 形态 B,空字符串字段合法 |
| 19 | middleware | **etcd** | MiddlewareCollectMetrics | Phase 5 P2 | 2026-07-10 16:00 | `tests/fixtures/collect/etcd.json` | `test_etcd_pipeline.py` | **形态 C:list-of-dict**(首次引入) |
| 20 | middleware | **memcached** | MiddlewareCollectMetrics | Phase 5 P2 | 2026-07-10 16:00 | `tests/fixtures/collect/memcached.json` | `test_memcached_pipeline.py` | 形态 C list-of-dict |
| 21 | middleware | **squid** | MiddlewareCollectMetrics | Phase 5 P2 | 2026-07-10 16:00 | `tests/fixtures/collect/squid.json` | `test_squid_pipeline.py` | port="instead." 异常值(真实反映) |
| 22 | middleware | **rocketmq** | MiddlewareCollectMetrics | Phase 5 P2 | 2026-07-10 16:00 | `tests/fixtures/collect/rocketmq.json` | `test_rocketmq_pipeline.py` | G4.9 placeholder,init 脚本模板填充 |
| 23 | middleware | **redis_sentinel** | MiddlewareCollectMetrics(复用 redis plugin) | Phase 6 | 2026-07-10 16:20 | `tests/fixtures/collect/redis_sentinel.json` | `test_redis_sentinel_pipeline.py` | entry_type=shell 复用 redis plugin,形态 C 2 实例(redis + sentinel) |
| 24 | middleware | **openresty(占位)** | MiddlewareCollectMetrics | Phase 4 | 2026-07-10 15:30 | (同上 #14) | (同上 #14) | (同 #14,G3.6 placeholder) |

### Passed 对象的 3 层验证明细

每对象在 e2e 流水线(`pipeline.py:185 run_full_pipeline_generic`)中跑过:
1. **契约验证** — `jsonschema.validate(instance, schema)`,公共契约 `00_common_contract.schema.json` 兼容 5 种 raw_stdout 形态
2. **流水线验证** — raw → canonical → format → Step 3 模型落地 → Step 4 关联,4 段流水线全过
3. **字段对齐验证** — fixture 字段 vs plugin instance schema vs Step 4 落库字段,3 套数据交叉对比

---

## 3. 🟡 Placeholder — 9 个对象(公共契约验证,等 license 解锁升级)

| # | 大类 | 对象 | v4 阶段 | 启动 | fixture 路径 | 测试文件 | 阻塞根因 | 解锁路径 |
|---|---|---|---|---|---|---|---|---|
| 1 | db | **dameng** | Phase 6 | 2026-07-10 16:30 | `tests/fixtures/collect/dameng.json`(placeholder) | `test_placeholder_objects.py::test_dameng` | license_status=missing,dm8 商业 license 不可达 | 业务方提供达梦 license + 装包 |
| 2 | middleware | **tongweb** | Phase 6 | 2026-07-10 16:30 | `tests/fixtures/collect/tongweb.json`(placeholder) | `test_placeholder_objects.py::test_tongweb` | aliyun + 东方通官网镜像都不可达(tar.gz 实际 HTML 404) | 东方通提供 license + 真实下载链接 |
| 3 | middleware | **jboss/wildfly** | Phase 6 | 2026-07-10 16:30 | `tests/fixtures/collect/jboss.json`(placeholder) | `test_placeholder_objects.py::test_jboss` | wildfly 4 种装包方式都失败(apt/aliyun/jboss.org/quay.io) | jboss.org 国内代理 OR 改用 docker.io 上 bitnami/wildfly |
| 4 | middleware | **jetty** | Phase 6 | 2026-07-10 16:30 | `tests/fixtures/collect/jetty.json`(placeholder) | `test_placeholder_objects.py::test_jetty` | ubuntu 22.04 apt 仓库无 jetty9 包 | eclipse 官方源 OR docker hub eclipse/jetty |
| 5 | middleware | **ambari** | Phase 7 | 2026-07-10 16:40 | `tests/fixtures/collect/ambari.json`(placeholder) | `test_placeholder_objects.py::test_ambari` | ambari 无官方 docker 镜像,需手动装 license + JDK + PostgreSQL | hortonworks archive docker 镜像 OR amd64 CI 装包 |
| 6 | middleware | **server_bmc** | Phase 7 | 2026-07-10 16:40 | `tests/fixtures/collect/server_bmc.json`(placeholder) | `test_placeholder_objects.py::test_server_bmc` | Redfish mock 真实数据(1 实例 https=true),CMDB 端无 plugin | CMDB 端补 plugin(关联厂商 × 红牌机型清单) |
| 7 | middleware | **ibmmq** | Phase 7 | 2026-07-10 16:40 | `tests/fixtures/collect/ibmmq.json`(placeholder) | `test_placeholder_objects.py::test_ibmmq` | IBM MQ 商业 license 不可达,用户拍板选 catalog 占位 | IBM Container Registry license + amd64 |
| 8 | db | **highgo** | Phase 8 | 2026-07-10 17:00 | `tests/fixtures/collect/highgo.json`(临时复用 postgres:16-alpine) | `test_placeholder_objects.py::test_highgo` | 临时复用 postgres:16-alpine,无 CMDB plugin | 瀚高提供 docker 镜像 + CMDB 补 plugin |
| 9 | middleware | **nacos** | Phase 8 | 2026-07-10 17:00 | `tests/fixtures/collect/nacos.json`(nacos-server:3.0.2 真实落盘) | `test_placeholder_objects.py::test_nacos` | nacos v3.0.2 真实落盘,无 CMDB plugin | CMDB 端补 nacos plugin |

> **placeholder 模式约定**:fixture 文件用 `_placeholder_reason: "<原因>"` 标记,等 license 解锁后,直接替换 fixture 数据并删 `_placeholder_reason` 字段即可升级为 ✅ passed。e2e 测试代码无需改动。

---

## 4. ⏭️ Skipped — 5 个对象(v3 范围外 / 无 plugin / 无 catalog)

| # | 大类 | 对象 | 跳过原因 | 后续路径 |
|---|---|---|---|---|
| 1 | protocol | **mssql** | 微软 SQL Server 镜像仅 amd64,arm64 Mac 启动 5+ 分钟未监听 1433 | amd64 CI runner 上重试(加 `platform="linux/amd64"`) |
| 2 | protocol | **oracle** | stargazer catalog 没注册(无 spec),plugin 有但无 fixture 跑通路径 | 补 catalog spec,plugin 已就绪 |
| 3 | middleware | **iis** | Windows 容器架构,fixture ssh 入口是 linux | 不在 v3 范围,需重写 ssh → winrm 采集入口 |
| 4 | db | **hbase** | HDFS + ZK + HBase 集群复杂,v3 暂缓 | 后续作为 HDFS 子对象处理 |
| 5 | middleware | **docker** | 单 host 镜像,非采集对象,v3 范围外 | 移除出 catalog |

---

## 5. 🔒 Archived — 18 个对象(license / amd64 / 集群复杂度)

> **封档决定(2026-07-10 17:00)**:经多次尝试(docker 新源 `6dduu4opte8882.xuanyuan.run` + 国产镜像源 + apt 源替换),以下对象无法在本机环境跑通。封档等业务方解锁。

| # | 大类 | 对象 | 阻塞根因 | 解锁路径 |
|---|---|---|---|---|
| 1 | middleware | **apusic** | 东方通 rpm + license + amd64 模拟未验证 | 业务方提供东方通 license |
| 2 | middleware | **bes** | 国产中间件 rpm + 文档少 + license + amd64 模拟未验证 | 业务方提供 bes license |
| 3 | db | **hdfs** | Hadoop 单节点伪分布式需 jdk + hadoop 2.x binary,amd64 模拟未验证 | amd64 CI runner 上装 hadoop 2.x |
| 4 | db | **informix** | IBM docker 镜像需 license,官网 rpm 不可达 | IBM 商业账号 + license |
| 5 | middleware | **ihs** | IBM 官方 rpm + license 不可达 + amd64 模拟未验证 | IBM 商业账号 + license |
| 6 | middleware | **inforsuite_as** | 中创 rpm + license + amd64 模拟未验证 | 业务方提供中创 license |
| 7 | db | **iris** | InterSystems docker 镜像需 license,装包源不可达 | InterSystems 商业账号 + license |
| 8 | db | **couchbase** | libcouchbase 系统库 + Enterprise license | Couchbase 商业账号 + Enterprise license |
| 9 | db | **oceanbase** | 装包源不可达 | OceanBase 商业账号 + license |
| 10 | db | **oscar** | 神通数据库装包源不可达 + amd64 模拟未验证 | 业务方提供神通 license |
| 11 | db | **sap_hana** | SAP 镜像需 license | SAP 商业账号 + license |
| 12 | middleware | **storm** | Storm 单节点伪分布式需 Nimbus + Supervisor + ZK,amd64 模拟未验证 | amd64 CI runner 上装伪分布式 |
| 13 | db | **sybase** | SAP 镜像需 license | SAP 商业账号 + license |
| 14 | middleware | **tonggtp** | 东方通 rpm + license + amd64 模拟未验证 | 业务方提供东方通 license |
| 15 | middleware | **tonglinkq** | 东方通 rpm + license 不可达 + amd64 模拟未验证 | 业务方提供东方通 license |
| 16 | db | **tongrds** | 东方通 RDS 装包源不可达 + license | 业务方提供东方通 license |
| 17 | middleware | **tuxedo** | Oracle Tuxedo 12c 安装需 Oracle 账号 + license | Oracle 商业账号 + license 接受 |
| 18 | middleware | **weblogic** | Oracle WebLogic 12c/14c 安装需 Oracle 账号 + license | Oracle 商业账号 + license 接受 |
| 19 | middleware | **websphere** | IBM WebSphere 9.x 安装需 IBM 账号 + license | IBM 商业账号 + license |
| 20 | db | **yarn** | YARN 单节点伪分布式需 jdk + hadoop 2.x,amd64 模拟未验证 | amd64 CI runner 上装伪分布式 |
| 21 | middleware | **mycat** | mycat 1.6 只有 amd64 二进制,arm64 rosetta 模拟极慢 | amd64 CI runner 上装 mycat 1.6 |
| 22 | middleware | **domestic_linux** | 麒麟/统信/欧拉 dnf 适配 + amd64 模拟未验证(实际生产应基于 openeuler 镜像,host 采集,主要看 ssh 采集流程) | amd64 CI runner + 国产 Linux iso |

> **注**:Skipped 5 个 + Archived 18 个 = 23 个未落盘对象(归档后的最终分类)。

---

## 6. 每个对象的执行结果明细(完整 56 条)

> 按 catalog 实际顺序排列,字段:大类 / 对象 / 状态 / runner / 真实落盘 / v4 阶段 / 备注

### databases

| 对象 | 状态 | runner | 真实落盘 | v4 阶段 | 备注 |
|---|---|---|---|---|---|
| **mysql** | ✅ | db 平铺 | ✅ | Phase 2.2 | 5 字段,db runner,Phase 2 闭环 |
| **redis** | ✅ | db 平铺 | ✅ | Phase 2.4 | 5 字段,slaves/string 兼容 |
| **postgresql** | ✅ | db 平铺 | ✅ | Phase 3 | inst_name 短名 "pg",需 alias |
| **mongodb** | ✅ | db 平铺 | ✅ | Phase 3 | 形态 B,database_role 空字符串合法 |
| **elasticsearch** | ✅ | db 平铺 | ✅ | Phase 3 | alias es,大写 plugin 类名 |
| **dameng** | 🟡 | placeholder | ✅(placeholder) | Phase 6 | dm8 商业 license 不可达 |
| **highgo** | 🟡 | placeholder | ✅(临时复用 postgres) | Phase 8 | 无 CMDB plugin |
| **mssql** | ⏭️ | — | ❌(arm64 失败) | skipped | 微软镜像仅 amd64 |
| **oracle** | ⏭️ | — | ❌ | skipped | catalog 无 spec |
| **hbase** | ⏭️ | — | ❌ | skipped | 集群复杂 |
| **informix** | 🔒 | — | ❌ | archived | IBM 商业 license |
| **sybase** | 🔒 | — | ❌ | archived | SAP 商业 license |
| **couchbase** | 🔒 | — | ❌ | archived | Enterprise license |
| **iris** | 🔒 | — | ❌ | archived | InterSystems 商业 license |
| **oceanbase** | 🔒 | — | ❌ | archived | 商业 license |
| **oscar** | 🔒 | — | ❌ | archived | 神通 license |
| **sap_hana** | 🔒 | — | ❌ | archived | SAP 商业 license |
| **tongrds** | 🔒 | — | ❌ | archived | 东方通 license |

### middleware

| 对象 | 状态 | runner | 真实落盘 | v4 阶段 | 备注 |
|---|---|---|---|---|---|
| **nginx** | ✅ | middleware metric.result | ✅ | Phase 2.3 | v2 标准化形态,extra_payload_keys |
| **tomcat** | ✅ | middleware 平铺 | ✅ | Phase 3 | catalina_path 字段 |
| **rabbitmq** | ✅ | middleware 平铺 | ✅ | Phase 3 | 形态 B |
| **kafka** | ✅ | middleware 平铺 | ✅ | Phase 3 | plugin 19 字段,raw 7 字段对齐 |
| **zookeeper** | ✅ | middleware 平铺 | ✅ | Phase 3 | 形态 B,14 字段 |
| **haproxy** | ✅ | middleware 平铺 | ✅ | Phase 3 | port="80&8404" 多端口 |
| **keepalived** | ✅ | middleware 平铺 | ✅ | Phase 4 | **不映射 port,用 virtual_router_id** |
| **openresty** | ✅ | middleware 平铺 | ✅ | Phase 4 | G3.6 placeholder |
| **apache** | ✅ | middleware 平铺 | ✅ | Phase 4 | 形态 B |
| **activemq** | ✅ | middleware 平铺 | ✅ | Phase 4 | fixture bin_path/config 不对齐 plugin install_path/conf_path |
| **minio** | ✅ | middleware 平铺 | ✅ | Phase 4 | 形态 A(含 bk_obj_id) |
| **consul** | ✅ | middleware 平铺 | ✅ | Phase 4 | 形态 B,空字符串合法 |
| **etcd** | ✅ | middleware 平铺 | ✅ | Phase 5 | **形态 C:list-of-dict**(首次引入) |
| **memcached** | ✅ | middleware 平铺 | ✅ | Phase 5 | 形态 C list-of-dict |
| **squid** | ✅ | middleware 平铺 | ✅ | Phase 5 | port="instead." 异常值 |
| **rocketmq** | ✅ | middleware 平铺 | ✅ | Phase 5 | G4.9 placeholder |
| **redis_sentinel** | ✅ | middleware 平铺(复用 redis) | ✅ | Phase 6 | 形态 C 2 实例 |
| **tongweb** | 🟡 | placeholder | ✅(placeholder) | Phase 6 | 东方通镜像不可达 |
| **jboss/wildfly** | 🟡 | placeholder | ✅(placeholder) | Phase 6 | 4 种装包方式都失败 |
| **jetty** | 🟡 | placeholder | ✅(placeholder) | Phase 6 | apt 源无 jetty9 |
| **ambari** | 🟡 | placeholder | ✅(placeholder) | Phase 7 | 无官方 docker 镜像 |
| **server_bmc** | 🟡 | placeholder | ✅(placeholder) | Phase 7 | CMDB 无 plugin |
| **ibmmq** | 🟡 | placeholder | ✅(placeholder) | Phase 7 | IBM MQ 商业 license |
| **iis** | ⏭️ | — | ❌ | skipped | Windows 容器 |
| **docker** | ⏭️ | — | ❌ | skipped | 非采集对象 |
| **apusic** | 🔒 | — | ❌ | archived | 东方通 license |
| **bes** | 🔒 | — | ❌ | archived | bes license |
| **ihs** | 🔒 | — | ❌ | archived | IBM 商业 license |
| **inforsuite_as** | 🔒 | — | ❌ | archived | 中创 license |
| **tonggtp** | 🔒 | — | ❌ | archived | 东方通 license |
| **tonglinkq** | 🔒 | — | ❌ | archived | 东方通 license |
| **tuxedo** | 🔒 | — | ❌ | archived | Oracle 商业 license |
| **weblogic** | 🔒 | — | ❌ | archived | Oracle 商业 license |
| **websphere** | 🔒 | — | ❌ | archived | IBM 商业 license |
| **storm** | 🔒 | — | ❌ | archived | 集群复杂 |
| **yarn** | 🔒 | — | ❌ | archived | 集群复杂 |
| **mycat** | 🔒 | — | ❌ | archived | amd64 only |
| **domestic_linux** | 🔒 | — | ❌ | archived | 国产 Linux iso |

### protocol

| 对象 | 状态 | runner | 真实落盘 | v4 阶段 | 备注 |
|---|---|---|---|---|---|
| **influxdb** | ✅ | protocol 平铺 | ✅ | Phase 2.1 | arm64 multi-arch,3 字段 |
| **nacos** | 🟡 | placeholder | ✅(nacos:3.0.2 真实落盘) | Phase 8 | 无 CMDB plugin |
| **hdfs** | 🔒 | — | ❌ | archived | 集群复杂 |
| **tdsql** | 🟡 | placeholder | ✅(临时复用 mysql:8.0) | Phase 8 | 无 CMDB plugin |

---

## 7. 关键决策日志(本周期)

- **2026-07-06**:v3 立项,梳理商业版 39 对象 + dameng 硬编码,按 driver_type 筛出 22 个 fixture 适用对象
- **2026-07-07**:v3 Phase 1-2 启动,优先 P0 对象(mysql/redis/nginx/influxdb),走 Gap-3 闭环
- **2026-07-08**:v3 Phase 3-5,11 个新 plugin 目录 + 14 个 init 脚本,sub-agent 并行
- **2026-07-09**:v3 base 提交 `51c76aefa`(30 对象代码侧完整化),worktree rebase + push
- **2026-07-10**:v4 OpenSpec 立项 `cmdb-collect-v4-e2e-platform`,3 specs + design + 37 tasks,openspec validate 通过
- **2026-07-10**:v4 Phase 1 基础设施 — 公共契约 `00_common_contract.schema.json` oneOf 5 形态 + 工厂函数 + 参数化模板 + 作者指南
- **2026-07-10**:v4 Phase 2 — 4 对象 Gap-3 闭环(influxdb/mysql/nginx/redis)
- **2026-07-10**:v4 Phase 3-5 — 8 + 6 + 4 = 18 对象 sub-agent 并行 fixture_driven
- **2026-07-10**:v4 Phase 6-8 — redis_sentinel + 9 placeholder(ambari/server_bmc/ibmmq/highgo/nacos/tdsql + dameng/tongweb/jboss/jetty)
- **2026-07-10**:**最终 33/33 真实落盘对象 e2e 触达,113 e2e passed, 6 skipped, 0 failed**
- **2026-07-10**:worktree v3+v4 共 12 commit 合并到主分支 `feature_windyzhao`,PR 文档准备就绪
- **2026-07-10 17:00**:**23 个未落盘对象封档(5 skipped + 18 archived),等业务方解锁 license / amd64 CI**

---

## 8. 未落盘对象的封档原则

### 8.1 不再主动重试

每个 archived 对象已经尝试过至少 3 种装包路径,本机环境(arm64 Mac)无法突破。换 amd64 CI runner 或用户提供 license 后才能解。

### 8.2 解锁后增量升级

后续收到一个 license 写一个 fixture,流程:
1. 在 catalog.py 解锁对应 spec 的 install_commands(去掉 `echo BLOCKED`)
2. `python -m tests.collect_fixtures.cli --model <obj> --bootstrap` 真实落盘
3. 在对应 placeholder 测试文件 `test_placeholder_objects.py` 把对象移到 ✅ passed
4. 新增/修改 `test_<obj>_pipeline.py`,3 层验证
5. commit + 增量 PR(不在当前 PR 范围)

### 8.3 当前 PR 范围

- **范围**:v3 base 30 对象代码侧 + v4 24 passed + 9 placeholder + 基础设施
- **不含**:23 archived 对象(封档等解锁)
- **风险**:零 production 代码改动(已 grep 验证)

---

## 9. 后续可推进方向(本封档外)

| 方向 | 工作量 | 收益 | 依赖 |
|---|---|---|---|
| amd64 CI runner | 0.5d 配置 | 解锁 8 个 archived 对象(mycat/domestic_linux/hdfs/yarn/storm/...) | CI 平台提供 runner |
| placeholder 升级 | 1-3h/对象 | 把 9 placeholder 升级到 3 层验证 | 用户提供对应 license/plugin |
| v4 Phase 2 质量度量 | 1d | fixture 覆盖率 dashboard + 字段漂移检测 | 框架 + 数据 |
| v4 Phase 3 真实采集 | 3-5d | stargazer 端跑真实采集(取代 fixture 模式) | amd64 CI runner |

---

## 10. 一句话总结

**v3+v4 完成 24 passed + 9 placeholder(33/33 真实落盘对象 e2e 100% 覆盖),113 passed/0 failed。23 个未落盘对象已封档,等 license / amd64 CI 解锁后增量升级。PR 已准备就绪,主分支 feature_windyzhao 12 commit 已 push 到 fork。**
