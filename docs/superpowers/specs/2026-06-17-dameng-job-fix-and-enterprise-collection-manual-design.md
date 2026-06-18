# 达梦(Dameng)JOB 采集链路修复 + 商业版配置采集插件接入手册 — 设计规格

- 日期:2026-06-17
- 作者:windyzhao（与 Claude 协作）
- 范围:CMDB 商业版（`cmdb_enterprise`）配置采集
- 关联方法论:`/systematic-debugging`（链路审计）、`/test-driven-development`（修复）

---

## 1. 背景与问题

商业版达梦数据库配置采集链路存在 **JOB / PROTOCOL 两套互相打架的定义**，导致采集任务运行时报错。经逐段审计（前端对象树 → 节点管理下发 → Stargazer 采集 → 回流格式化入库），确认链路不完整。

### 1.1 链路逐段现状

| 链路段 | 文件 | 状态 |
|---|---|---|
| ① 采集对象树 | `apps/cmdb_enterprise/collect/tree.py` | ✅ `task_type=DB`、`type=JOB` |
| ② 指标映射 | `apps/cmdb/collection/constants.py:143` `DB_COLLECT_METRIC_MAP["dameng"]=["dameng_info_gauge"]` | ✅ |
| ③ Stargazer 采集插件 | `agents/stargazer/enterprise/plugins/inputs/dameng/` | ✅ job 脚本，`default_executor: job`，仅定义 job executor |
| ④ NodeParams 下发 | 见断点 B / 隐患 C | ❌ |
| ⑤ 回流格式化插件 | 见断点 A | ❌ |

### 1.2 三处缺陷（根因）

**🔴 断点 A — 格式化插件注册槽位错误。**
`apps/cmdb_enterprise/collect/dameng.py` 的 `DaMengCollectionPlugin` 继承 `BaseProtocolCollectionPlugin`（`apps/cmdb/collection/plugins/community/protocol/base.py:7` 设 `supported_task_type = PROTOCOL`），故注册到 `(PROTOCOL, "dameng")`。但运行时 `JobCollect` 的 DB 路径（`collect_tasks/job_collect.py:21` → `DBCollect` → `collect_tasks/databases.py:11`）按 `get_collection_plugin(task.task_type=DB, "dameng")` 查找，registry（`plugins/registry.py:57`）找不到 `(DB,"dameng")` → 抛 `ValueError: Unsupported collection plugin`。
对照：所有 JOB 类数据库（db2/es/hbase/mongodb/tidb）均继承 `BaseDBCollectionPlugin`（`supported_task_type=DB`），仅 dameng 用错基类。

**🔴 断点 B — 下发的 executor_type 与 Stargazer 插件不匹配。**
`apps/cmdb_enterprise/collect/dameng.py` 的 `NodeParams` 继承裸 `BaseNodeParams`，`executor_type` 默认 `"protocol"`（`node_configs/base.py:62`），端口默认写成 `3306`（MySQL 端口，达梦应为 5236）。下发后 Stargazer 去找 dameng 的 `protocol` executor，但其 `plugin.yml` 只有 job executor → 执行器解析失败。

**🟠 隐患 C — 两个 dameng NodeParams 重复注册、互相覆盖。**
两个 `supported_model_id="dameng"` 的 NodeParams 都未设 `supported_driver_type`，都注册到同一 key `(dameng, None)`（`node_configs/base.py:39`），后导入者静默覆盖：
- `apps/cmdb/node_configs/databases/dameng.py:9` `DaMengNodeParams(SSHNodeParamsMixin)` → executor_type=**job**（正确）
- `apps/cmdb_enterprise/collect/dameng.py:32` `NodeParams` → executor_type=**protocol**（错误）

---

## 2. Part 1 — 达梦修复：统一为 JOB 类型

### 2.1 决策

**单一事实来源 = JOB。** 依据:已有可用的 job 采集脚本 + 对象树声明 JOB + DB 指标映射齐备。不引入 protocol 路径（避免给 Stargazer 重复造 Python collector）。

NodeParams 落位决策(已确认):**收敛进企业包** —— 把正确的 SSH/job NodeParams 移入 `cmdb_enterprise/collect/dameng.py`，删除 `community/node_configs/databases/dameng.py`，使达梦所有企业代码集中在企业包内，经 `node_param_packages` 自动发现。

### 2.2 改动清单

| # | 改动 | 文件 |
|---|---|---|
| 1 | `DaMengCollectionPlugin` 基类 `BaseProtocolCollectionPlugin` → `BaseDBCollectionPlugin`；`inst_name` 映射由 `ProtocolCollectMetrics.get_inst_name` 改为 `BaseDBCollectionPlugin.get_inst_name`（两者产物均为 `f"{ip_addr}-{model_id}-{port}"`，行为等价） | `apps/cmdb_enterprise/collect/dameng.py` |
| 2 | 删除该文件中 protocol 版 `NodeParams` 类 | 同上 |
| 3 | 在该文件中新增 SSH/job 版 NodeParams（继承 `SSHNodeParamsMixin, BaseNodeParams`，`supported_model_id="dameng"`、`plugin_name="dameng_info"`，复用 mixin 的 job 凭据/env/executor_type=job） | 同上 |
| 4 | 删除 `apps/cmdb/node_configs/databases/dameng.py` | community 包 |

修复后唯一注册：`(DB, "dameng")` 格式化插件；`(dameng, None)` job NodeParams。`NodeParamsFactory.get_params_class("dameng","job")` 命中回退键 `(dameng, None)`，返回 job 类。

### 2.3 不需要改动

- 对象树（已是 DB/JOB）。
- `DB_COLLECT_METRIC_MAP`（`dameng_info_gauge` 与 `plugin_name="dameng_info"` 约定一致，与 db2/es/tidb 同构）。
- Stargazer 插件（job 脚本可用）。
- 指标查询/入库管线（与其它 JOB 库共用）。

### 2.4 测试（TDD：先红后绿）

遵循 `server/docs/testing-guide.md` 分层，置于 `apps/cmdb_enterprise/tests/`：

- **`_pure`（无 DB/IO）**
  - `DaMengCollectionPlugin.supported_task_type == CollectPluginTypes.DB`
  - registry 快照中存在 `(DB,"dameng")`，且**不存在** `(PROTOCOL,"dameng")`
  - `metric_names == ("dameng_info_gauge",)`；`field_mapping` 含 `inst_name/ip_addr/port/version/dm_*` 关键字段
- **`_service`（mock 依赖）**
  - `NodeParamsFactory.get_params_class("dameng","job")` 返回 job 类，且实例 `executor_type == "job"`
  - `set_credential()` 产出 `node_id`/`password` env（不含 port=3306）
  - 全局仅一个 `supported_model_id=="dameng"` 的 NodeParams 注册（无重复覆盖）
- **对象树**
  - `get_collect_obj_tree()` 中 databases 下存在 dameng 且 `type == JOB`

验证命令:`cd server && uv run pytest apps/cmdb_enterprise/tests/ -v`。修复前相关用例应红，修复后全绿。

---

## 3. Part 2 — 商业版配置采集插件接入手册（独立完整手册）

### 3.1 定位与落位

- 类型:**独立完整手册**，不依赖社区版 `apps/cmdb/collection/CMDB配置采集插件开发指南.md`，从零覆盖企业版全链路。
- 路径(已确认):`server/apps/cmdb_enterprise/商业版配置采集插件接入手册.md`
- 贯穿范例:**修复后的达梦**（正确的 JOB/DB 接法）。

### 3.2 目录结构

1. **概述与适用范围** — 商业版↔社区版架构关系、扩展契约理念、读者前置要求
2. **整体架构与四段调用链路** — 对象树 → 节点下发 → Stargazer 采集 → 回流格式化入库（含链路图/时序）
3. **企业版扩展机制详解** — `apps/cmdb/extensions` 注册表、`apps/cmdb/collect/extensions.py` collect 门面契约、`cmdb_enterprise/registry_hooks.py` 注册时机；collect 契约三件套:`collect_tree` / `plugin_packages` / `node_param_packages`；社区↔企业插件 `priority` 覆盖规则
4. **接入步骤**
   - 步骤 0:采集对象树增量(`collect/tree.py` + `ENTERPRISE_COLLECT_OBJ_TREE`；`task_type`(DB/HOST/MIDDLEWARE/PROTOCOL…) 与 `type`(job/protocol) 取值；`encrypted_fields`；合并逻辑 `services/collect_object_tree.py`)
   - 步骤 1:NodeParams 下发(SSH/job vs protocol 两种；`set_credential`/`env_config`/`executor_type`/`host_field`；`plugin_name` 与指标命名约定 `{name}_info_gauge`；`__init_subclass__` 自动注册与 `(model_id, driver_type)` key)
   - 步骤 2:指标映射(`DB_COLLECT_METRIC_MAP` / `MIDDLEWARE_METRIC_MAP` / `PROTOCOL_METRIC_MAP` / `HOST_COLLECT_METRIC`)
   - 步骤 3:回流格式化插件(继承正确基类 —— `BaseDBCollectionPlugin`/`BaseMiddleware...`/`BaseProtocolCollectionPlugin`；**`supported_task_type` 必须与 tree.type 一致**；`field_mapping` 三种用法:字符串/元组/函数；`priority` 覆盖)
   - 步骤 4:Stargazer 采集插件(`enterprise/plugins/inputs/{model}/plugin.yml`；job executor + shell 脚本 或 protocol executor + Python collector；`PluginSourceResolver` 企业优先、OSS 回退)
5. **关键一致性约束** — task_type 三处必须一致:`tree.type` ↔ `plugin.supported_task_type` ↔ stargazer executor;`plugin_name` ↔ `{name}_info_gauge`;`model_id` 全链路一致。以达梦曾经的 bug（断点 A/B/C）作反面教材
6. **完整范例:达梦端到端接入** — 贴修复后的正确代码（对象树/NodeParams/指标/格式化插件/Stargazer 插件）
7. **测试规范** — pytest 分层、注册校验、节点下发参数校验、对象树合并校验（引用 Part 1 测试为样板）
8. **排错手册** — `Unsupported collection plugin`(task_type 错配)、executor 解析失败(executor_type 与 plugin.yml 不符)、重复注册静默覆盖、指标查不到(metric/plugin_name 不匹配)

---

## 4. 实施顺序

1. Part 1 修复（TDD：先写测试 → 改代码 → 转绿）
2. 跑 `apps/cmdb_enterprise/tests/` 验证全绿
3. Part 2 手册（以修复后的达梦真实代码为范例，确保文档与代码一致）

## 5. 验收标准

- `uv run pytest apps/cmdb_enterprise/tests/ -v` 全绿，含新增达梦注册/下发/对象树用例。
- registry 中 dameng 仅注册于 `(DB,"dameng")`；NodeParams 仅一处、executor_type=job。
- 手册落位且四段链路、扩展机制、一致性约束、达梦完整范例齐备，代码片段与仓库现状一致。

## 6. 超出范围（YAGNI）

- 不为达梦新增 protocol 执行路径 / Python collector。
- 不改造其它数据库插件。
- 不重写社区版开发指南。
- 达梦端口默认值(5236)仅在新 job NodeParams 中按 SSH 凭据语义处理，不引入 protocol 端口配置。
