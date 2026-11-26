# 内置采集器预置配置随模板刷新

Status: implemented

需求来源：p398_1057 的存量生效路径。机制对所有内置采集器的 `default_config` 变化生效，本迭代的第一笔变化是 Linux Vector 的 Trap 处理段。

决策记忆：`docs/design/product-decisions/log-extractor-passive-collect.md`。

既有补齐规格 `specs/changes/node-mgmt-builtin-collector-backfill/spec.md` 仍负责「新建采集器、给还没有配置的节点补一行」，本规格不改它。

## Problem Statement

改 `support-files/collectors/*.json` 的 `default_config` 后，`node_init` 会更新 `Collector.default_config`，已纳管节点上的预置 `config_template` 保持旧正文。Trap 的三个新字段写在 Vector 模板里，不刷新就只对之后新纳管的容器节点生效。

`repair_node_config` 会重绑架构、重写每个节点上全部默认采集器的预置配置，并逐节点投递汇聚任务。迁移在 `node_init` 之前执行，当时目录还是旧模板，失败还会拦住整个容器，而且每改一次模板就要再写一条迁移。

## Solution

`import_collector` 每次启动都会读出全部采集器。对已存在的采集器，比较库中的 `default_config` 和文件里的 `default_config`：

- 相同：什么都不做，不查节点。
- 不同：在 `import_collector` 里同步刷新该采集器的预置配置，成功后再把新的 `default_config` 写进目录。

刷新完成后目录等于文件，之后的启动只剩内存比较。

## User Stories

1. 作为升级后的环境，`node_init` 结束时，容器节点上已有的 Vector 预置正文已是新模板；Sidecar 下次心跳拉到后，新 Trap 带上 `source_ip`、`cloud_region_id`、`agent_addr`。
2. 作为下次发版，模板没变时初始化不查节点配置。
3. 作为改过自定义配置的用户，我的 `is_pre=False` 配置保持原样。直接改过的预置正文在该采集器模板变化时被模板结果覆盖。
4. 作为运维，某个采集器刷新失败不挡住服务启动；下次启动自动重做。

## Implementation Decisions

### D1. 比较

- 位置：`server/apps/node_mgmt/management/services/node_init/collector_init.py` 的 `import_collector`，只处理 `update_collectors`。
- 左：本轮 `Collector.objects.all()` 已加载行上的 `default_config`。复用已有查询结果，不为比较再查库。
- 右：文件里同一 `id` 的 `default_config` 字典。
- 判定：字典不相等。键顺序无关。只比 `default_config`，其它字段不参与。
- 只对 `controller_default_run=True` 的采集器刷新。其余采集器 `default_config` 变了照常写目录，不查节点。

### D2. 刷新（每个变化的采集器）

先改节点，后写目录。

1. 查 `CollectorConfiguration`：`collector_id` 等于该采集器，`is_pre=True`，按 `id` 排序，每批 500 行，用 `id > 上一批最后 id` 翻页。只取 `id`、`config_template`。绑定节点用一次预取，只取判定容器和区域需要的字段：`id`、`node_type`、`tags`、`cloud_region_id`。
2. 用新的 `default_config` 渲染。按 `(节点 cloud_region_id, 是否容器节点)` 分组，一组只渲染一次。区域环境变量按区域缓存。
3. 渲染函数复用 `server/apps/node_mgmt/services/collector_default_backfill.py` 的 `render_builtin_default_template`。它与首次纳管 `Sidecar.create_default_config` 落库的那一步相同：Jinja 只吃区域环境变量，`${node.ip}`、`${node.cloud_region}`、`${NATS_*}` 原样留在正文里，Sidecar 拉取时才替换。不得调用 `Sidecar.render_template`。`render_builtin_default_template` 接收采集器对象，用一个只改了 `default_config` 的临时对象或等价方式传入新字典，不先写库。
4. 容器判定复用同文件的 `_is_container_node`。允许把它和 `_load_region_env` 改成公开名供两处使用，不复制实现。
5. 不写的情况：
   - 渲染结果与 `config_template` 相同。
   - 渲染结果为 `None`（容器专用采集器遇到非容器节点，或没有可渲染模板）。不得把正文改成空。
   - 没有绑定节点。
   - 同一配置绑定的节点在「区域 + 是否容器」上不一致。
6. 有差异的行一批一次 `bulk_update(["config_template"])`。不改 `cloud_region`、名称、`is_pre`、`env_config`。
7. 写完后对本批改过的配置 id 调用 `apps.node_mgmt.services.sidecar_cache.invalidate_configuration_etags`。`bulk_update` 不触发 `post_save`，必须显式调用。清除失败只记 warning，不算刷新失败；ETag 缓存 5 分钟过期。

刷新不给还没有该采集器配置的节点新建配置，不调用 `Sidecar.create_default_config`、`repair_node_config`，不投递 Celery 任务，不重启采集器。

### D3. 失败与重试

- 以采集器为单位。某个采集器刷新时抛出任何异常：记一条 ERROR，持有 traceback，带 `collector_id`、`failed_stage`（`load` / `render` / `write`）、`error_type`。该采集器本轮 `default_config` 保持库中旧值，其它字段照常更新。继续处理其它采集器，`batch_init` 不失败。
- 下次启动该采集器两边仍不相等，再刷一遍。已写成新正文的行渲染结果相同，被跳过。
- 刷新失败期间新纳管节点仍拿旧模板，直到下次刷新成功。
- 多个 Server 副本同时初始化写出相同结果，可重复执行。

### D4. 日志

每个变化的采集器记一条 INFO 汇总，稳定模板加惰性参数：

```text
event=collector_preset_refresh_completed collector_id=%s checked=%s updated=%s skipped=%s elapsed_ms=%s
```

不逐行打 INFO，不记录正文、环境变量或节点 IP。跳过不一致绑定时可以在 DEBUG 记配置 id。日志用 `from apps.core.logger import node_mgmt_logger as logger`。`collector_init.py` 现有 import 是 `node_logger`，新逻辑与已有补齐服务一致用 `node_mgmt_logger`，需确认两者在 `apps/core/logger.py` 中都存在后再选。

### D5. 范围说明

- 自定义配置（`is_pre=False`）和子配置不读。
- 直接改过的预置正文会被模板结果覆盖。要保留改动，另存为自定义配置。节点配置接口今天仍允许改预置正文，本规格不收紧那个接口。
- `add_config` 只拼给容器节点，规则与首次纳管相同。
- 新建采集器路径和 `CollectorDefaultBackfill` 不变。

### D6. 本迭代的模板变化：Trap 三个字段

只改 `server/apps/node_mgmt/support-files/collectors/Vector.json` 里两份 Linux 模板（`Vector_linux`、`Vector_linux_arm64`）的 `default_config.add_config`，并且只改 `transforms.snmp_trap_parse` 的 VRL。不要改 `transforms.syslog_enrich_base`。Windows 的 `add_config` 保持空。不改 `Snmptrapd.json`，不改 `agents/fusion-collector/agent/snmptrap-to-socket`，不发采集器镜像。

在去掉 `snmptrapd: ` 包装头之后的原文上补三个字段。三个字段始终赋值。解析不到写成 `""`，不用 null，不回退成 `node_ip`。

- `source_ip`：匹配以 `UDP:`、`UDP/IPv6:` 或 `TCP:` 开头的传输地址行，取该行第一个方括号内的地址。校验为合法 IPv4 或 IPv6 后写入。按行内容匹配，不写死行号。兼容 `UDP: [a]:p->[b]:162`、`UDP: [a]:p`、`UDP/IPv6: [a]:p->[b]:162`、`TCP: [a]:p->[b]:162`。没有这一行、括号内不是合法 IP、或解析失败：`""`。不得改用 `agent_addr`。
- `cloud_region_id = "${node.cloud_region}"`，带引号，与 syslog 相同。占位符必须是 `${node.cloud_region}`；`${node.cloud_region_id}` 不会被替换。
- `agent_addr`：变量绑定名称 `snmpTrapAddress.0` 或数字 OID `1.3.6.1.6.3.18.1.3.0`（含前导点写法，以及未加载 MIB 时的 `iso.3.6.1.6.3.18.1.3.0`），值是合法 IPv4 或 IPv6 时写入，否则 `""`。不覆盖 `source_ip`。不按 SNMP 版本分支。
- `node_ip` 保持 `${node.ip}`，语义仍是接收节点。
- VRL 里所有可失败调用要处理错误，让 Vector 能加载配置。注意 `add_config` 会经过 Jinja 渲染：VRL 里不得出现 `{{`、`{%`、`{#`。正则里的花括号量词要避开或改写。

`server/apps/log/support-files/plugins/Snmptrapd/network/collect_type.json` 的 `attrs` 增加这三个字段。`default_query` 不变。现有日志初始化会同步该文件，不另写迁移。

修正 `specs/capabilities/legacy-fuctionlist-04-日志系统-功能清单.md` 的 snmp_trap 一节：`node_ip` 是接收节点 IP；补上这三个字段；正文是 `message`，去掉 `trap_message`、`raw_message`。

不把 Trap 写入 `SyslogSourceDevice`，不改「集成 / 来源设备」。来源清单、品牌、型号、设备类型仍在 p398_1059。历史日志不回填。

## 验收

1. 目录 `default_config` 未变：`import_collector` 不查 `CollectorConfiguration`（用查询计数断言）。
2. 只改一个采集器的 `default_config`：只有该采集器的预置正文被改写；另一采集器的预置正文不变。
3. 容器节点的预置正文含新 `add_config`，且 `${node.cloud_region}`、`${node.ip}` 仍是字面占位符。非容器节点的预置正文在基础段没变时不被写。`is_pre=False` 配置不变。子配置不变。
4. 预置正文被人手改过：被模板结果覆盖。渲染结果相同：不写，也不清 ETag。
5. 改写后相关配置 ETag 被清除，测试不依赖 `post_save`。
6. 刷新抛异常：`import_collector` 不抛出；该采集器库中 `default_config` 仍是旧值，其它字段已更新；另一采集器正常刷新；ERROR 只有一条且带 `collector_id`、`failed_stage`、`error_type`。下一次导入同一文件时重做并成功。
7. 同一文件再次导入：不再查节点配置。
8. 新建采集器仍写 `CollectorDefaultBackfill`，补缺失行为不变。
9. 5000 条预置配置的刷新在 sqlite 测试中可完成，记录耗时（不作为硬阈值断言，写进交付说明）。查询次数随批次线性增长，不随行数线性增长。
10. Trap 解析：`Vector.json` 两份 Linux 模板的 `snmp_trap_parse` 文本一致；`syslog_enrich_base` 与改动前逐字相同；Windows `add_config` 仍为空；`default_query` 不变。若本机有 `vector` 二进制，用 `vector vrl` 或 `vector test` 跑四种传输地址行、非法括号、缺失行、带和不带 `agent_addr` 的样本；没有则在交付说明里写明未跑，并给出样本和期望值。
11. Trap 采集类型 `attrs` 含三个新字段。

验证命令：

```text
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/node_mgmt/tests/test_collector_default_backfill.py apps/node_mgmt/tests/test_collector_preset_refresh.py --no-cov
```

## 明确不做

- 不新增命令、模型字段、迁移、Celery 任务。
- 不在迁移里改节点配置。
- 不调用 `repair_node_config`。该命令保持原样。
- 不收紧节点上编辑预置正文的接口。
- 不把 `add_config` 拼给非容器节点。
- 不改 p398_1059。

## 改动文件

- `server/apps/node_mgmt/management/services/node_init/collector_init.py`：比较、刷新、按结果决定是否写新 `default_config`。
- `server/apps/node_mgmt/services/collector_default_backfill.py`：只在需要时把容器判定、区域环境缓存改为可复用的公开函数。刷新函数可放在这里或新文件 `server/apps/node_mgmt/services/collector_preset_refresh.py`。
- `server/apps/node_mgmt/tests/test_collector_default_backfill.py`：`test_update_existing_collector_does_not_schedule_backfill_or_rewrite_config` 改为「不写补齐记录，但改写预置正文」。
- `server/apps/node_mgmt/tests/test_collector_preset_refresh.py`：验收 1–9。
- `server/apps/node_mgmt/support-files/collectors/Vector.json`：两份 Linux Trap 段。
- `server/apps/log/support-files/plugins/Snmptrapd/network/collect_type.json`：三个 attr。
- `specs/capabilities/legacy-fuctionlist-04-日志系统-功能清单.md`：snmp_trap 字段一节。
