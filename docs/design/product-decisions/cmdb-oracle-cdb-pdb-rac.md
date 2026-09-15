# Oracle 配置采集产品决策记忆

- 最近更新：2026-09-15
- 当前规格：`specs/changes/cmdb-oracle-cdb-pdb-rac/spec.md`

## 产品定位

Oracle 配置采集要覆盖传统非 CDB、CDB/PDB 和 RAC，做成可入库的资产清单，而不是把优云的表空间 / ASM / Redo 子树搬进来。

## 已确认范围

- 保留 `oracle` 为库和采集任务根。
- 新增 `oracle_instance`、`oracle_pdb` 两个子模型。
- 有无 CDB、PDB、RAC 都兼容；采集按连上的容器识别，不预判拓扑。

## 已确认设计决策

- CDB 就是 `oracle`，RAC 是多条 `oracle_instance`，不另建 `oracle_cdb` / `oracle_rac`。
- 单机非 CDB 也落 1 条 `oracle_instance`；没有 PDB 时不创建 PDB 实例，这是空清单不是失败。
- 父模型 IP/端口/SID/服务名是本次接入点。身份用 `db_unique_name`，避免 `{ip}-oracle` 碰撞。
- 连接支持 SID 与 Service Name；连不上或鉴权失败才失败。
- 协议采集默认不删未见子对象，避免 PDB 账号把兄弟对象清掉。

## 明确后置

- SSH 本地发现。
- 表空间 / ASM / Redo / Schema。
- Data Guard 集群对象。
- CDB 全量范围下删除未见子对象。
- SCAN 作为独立 CI。

## 仍待确认

无。

## 已替代决策

- 2026-09-15 原先「单模型修身份即可」已改为：保留 oracle，新增实例和 PDB 子模型。
- 2026-09-15 原先「必须 common user 连 CDB」已改为：CDB 与 PDB 账号都兼容，范围不足时降级落盘。

## 决策来源

- 用户于 2026-09-15 确认：保留原模型、新增两个子模型、有无 CDB/PDB 都兼容，并批准定稿实现。
