# Oracle CDB / PDB / RAC 配置采集

Status: ready

## Problem Statement

运维要把一套 Oracle 作为资产入库，但现场既有传统非 CDB，也有 CDB/PDB 和 RAC。当前只有一个 `oracle` 模型，身份还写成 `{ip}-oracle`，同一主机上的多实例和 PDB 会互相覆盖。

## Solution

保留现有 `oracle` 作为库和采集任务根，新增 `oracle_instance`、`oracle_pdb`。采集按连上的容器自动识别，有无 CDB/PDB/RAC 都成功落盘，不要求客户先勾拓扑。

## User Stories

1. As a CMDB 管理员, I want 继续用 oracle 建采集任务, so that 监控联动和应用拓扑不用换模型
2. As an 运维人员, I want 非 CDB 环境采到 1 个库和 1 个实例、0 个 PDB, so that 传统库不会被当成失败
3. As an 运维人员, I want 连到 CDB 根时看到全部实例和业务 PDB, so that RAC 和多租户清单是全的
4. As an 运维人员, I want 只有 PDB 账号时仍能入库当前库、当前实例和当前 PDB, so that 没有 common user 也能先采上
5. As an 运维人员, I want 实例身份按库唯一名加 SID, PDB 按库唯一名加 PDB 名, so that 先 PDB 再 CDB 采会收敛到同一套对象

## Implementation Decisions

- 采集任务、监控对象绑定仍用 `oracle`。父模型现有 IP/端口/SID/服务名表示本次接入点，不是 RAC 节点清单。
- 新增子模型 `oracle_instance`、`oracle_pdb`，分类 database，应用拓扑层级为应用服务层。
- 父模型身份改为 `db_unique_name`（空则 `db_name`）。实例 `{db_unique_name}-{sid}`，PDB `{db_unique_name}-{pdb_name}`。单机也落 1 条实例。
- 连接同时支持 SID 与 Service Name，不再默认 `orclpdb`。
- 连上后用 `CON_NAME`、`v$database`、`v$pdbs`、`gv$instance` 判断：`collect_scope` 为 `cdb` / `pdb` / `non_cdb`。无 `v$pdbs` 是非 CDB；`gv$` 失败退回 `v$instance`。
- 协议采集默认不删除未见子对象，因此 PDB 范围采集不会清掉兄弟 PDB 或 RAC 节点。
- 跳过 `PDB$SEED`。表空间 / ASM / Redo、Data Guard 集群对象、SCAN CI、单独的 `oracle_cdb` / `oracle_rac` 不做。

## Testing Decisions

- 好测试只验证：拓扑识别字面量、非 CDB / CDB 根 / 仅 PDB 的落盘键、身份拼接、SID 与 Service Name 建连、模型种子含两个子模型和 belong 关联。
- 约定接缝：
  - `oracle_topology` 纯函数
  - `OracleInfo.list_all_resources`（mock SQL）
  - `OracleCollectionPlugin` 字段映射与 metrics
  - `model_config.xlsx` 模型/属性/关联种子
- Prior art：`test_db_plugins_native_async.py`、`test_new_collect_objects_model_config.py`

## Out of Scope

- SSH 本地发现 ORACLE_HOME / listener
- 表空间、ASM、Redo、Schema 子模型
- Data Guard 作为独立集群对象
- CDB 范围采集后删除未见子对象
- 现网 `{ip}-oracle` 实例原地改名迁移

## Further Notes

- 已按 `{ip}-oracle` 入库的数据需要重采。
- `max_mem` 继续用该字段名，取值改为 `sga_max_size`（空则 `memory_target`）。
