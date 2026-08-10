# 云平台子对象采集扩充

> Migrated from `spec/requirements/CMDB/20260619.云平台子对象采集扩充.md` as legacy capability evidence.

日期：2026-06-19
范围：华为云、OpenStack、ManageOne 三个云平台的子对象建模与配置采集扩充（**不含 SmartX**）
关联前序：

> **范围修订（2026-06-19，并行代码/官方文档核证后）**：原拟 17 个新对象，经 grounded 核证后定为 **14 个**（华为云 9 + OpenStack 4 + ManageOne 1）。剔除 3 个无法在「驱动实际返回 / 官方文档」中落地的对象，理由见各平台章节与「约束与边界」。这是「字段不杜撰、查不到就不做」铁律的直接结果。
[20260608.配置采集新增达梦KeepAlive及私有云平台.md](20260608.配置采集新增达梦KeepAlive及私有云平台.md)、设计文档 [2026-06-11-cmdb-collection-six-plugins-design.md](../../../docs/superpowers/specs/2026-06-11-cmdb-collection-six-plugins-design.md)

## 背景与问题

上一期（20260608）为 6 个云平台补齐了「平台 + 核心计算/存储」子对象的配置采集。但相比已内置的公有云（腾讯云 14 类、AWS 10 类、阿里云 8 类子对象），这几个新平台的子对象覆盖明显偏薄：

- 华为云：当前**仅 `hwcloud_ecs`** 一个子对象。
- OpenStack：仅 node/vm/vg/sp（计算+块存储），**无网络层**。
- ManageOne：cloud/server/host/ds/elb，**无浮动 IP、ELB 监听池/成员**。
- FusionInsight：仅 cluster/host，**无数据存储 ds**。

而底层驱动（`agents/stargazer/common/cmp/cloud_apis/resource_apis/cw_*.py`）实际已经能拉到远多于此的资源——华为云驱动已含 `list_disks/list_buckets/list_vpcs/list_subnets/list_eips/list_security_groups/list_load_balancers` 等。瓶颈在「模型缺失 + 采集器未接」，不在驱动能力。

本期目标：在**不触碰任何存量对象**的前提下，为上述 4 平台**新增子对象模型 + 配置采集**，把网络、块存储、对象存储、负载均衡、托管数据库等类别补齐，使其子对象覆盖向公有云看齐。

## 铁律（全程强约束）

1. **存量对象一律不动**：既有模型（`attr-*`/`asso-*` 表）、既有采集器对存量对象的输出分支、既有 `field_mappings`/`metric_names` 条目，全部保持原样。本期是**纯增量**。
2. **关联只新建、不改存量**：每条新关联的**源模型必须是新对象**。`asso-<model>` 表按源模型组织，只新建 `asso-<新对象>` 表；即便挂到存量对象（如云硬盘挂 ECS），也是 `源=新对象 → 目标=存量对象`，存量对象自己的表零改动。存量对象只能作为关联**目标**出现。
3. **字段不杜撰**：每个新对象的字段一律取自「驱动 `handle_*` 实际返回」或「官方 API 响应文档」。驱动只返回原始 API 对象的，实现时读真实返回 + 对照官方文档逐字段确认字段名/单位。官方文档查不到列实例 API 或字段的对象，本期不做。
4. **完成后不 commit**，由用户本人提交。

## 需求描述

### 1）华为云 hwcloud（新增 9 个子对象，富模板）

| 新模型 | 模型名称 | 驱动来源 | 复用图标 |
|---|---|---|---|
| `hwcloud_evs` | 华为云云硬盘 | `list_disks`（已有） | cc-cloud-sp_云存储 |
| `hwcloud_obs` | 华为云对象存储桶 | `list_buckets`（已有） | cc-cloud-sp_云存储 |
| `hwcloud_vpc` | 华为云VPC | `list_vpcs`（已有） | 网络类图标 |
| `hwcloud_subnet` | 华为云子网 | `list_subnets`（已有） | 网络类图标 |
| `hwcloud_eip` | 华为云弹性公网IP | `list_eips`（已有） | 参照 qcloud_eip |
| `hwcloud_sg` | 华为云安全组 | `list_security_groups`（已有） | 网络类图标 |
| `hwcloud_elb` | 华为云负载均衡 | `list_load_balancers`（已有） | cc-cloud-elb_云负载均衡 |
| `hwcloud_rds` | 华为云数据库RDS | **新增驱动 `list_rds`**（官方 [ListInstances](https://support.huaweicloud.com/api-rds/rds_01_0004.html)） | cc-mysql_MySQL |
| `hwcloud_dcs` | 华为云分布式缓存Redis | **新增驱动 `list_dcs`**（官方 [DCS API](https://support.huaweicloud.com/api-dcs/dcs-api-0514011.html)） | cc-redis_REDIS |

华为 7 个网络/存储/ELB 对象的驱动方法（`list_disks/buckets/vpcs/subnets/eips/security_groups/load_balancers`）经核证**均返回归一化 dict**（由 `cloud_object/base.py` 模型类 `to_dict()` 决定的固定键集），字段直接取自这些归一化键。`hwcloud_rds` 字段以官方 ListInstances 响应为准（`id, name, status, type, datastore.type/version, volume.type/size, region, vpc_id, subnet_id, private_ips[0], public_ips[0], cpu, mem, created, charge_info.charge_mode`）；`hwcloud_dcs` 取官方 DCS V2 列实例响应（`instance_id, name, status, engine, engine_version, capacity, ip, port, vpc_id, subnet_id, charging_mode, created_at, cache_mode`——注意是 `charging_mode`/`created_at`，无 `region`）。

### 2）OpenStack（新增 4 个网络对象）

`openstack_vpc`、`openstack_subnet`、`openstack_eip`、`openstack_sg`。块存储已有 vg/sp，本期不重复。

> **实现要点**：in-tree 采集器 `openstack_info.py` 是**自包含的 Keystone v3 / Neutron REST 客户端（用 `requests`，不走 cw_openstack SDK 驱动）**。因此网络对象需照其 `get_resource_uri` + `list_<x>` + `handle_<x>` + `_map_<x>` 三段式，新增对 Neutron（`:9696`）的 REST 调用；字段对照 OpenStack 开放 Neutron API 文档（network/subnet/floatingip/security-group）逐项确认。关联键：`subnet.network_id → vpc`。零驱动（SDK）改动，但采集器需新增 REST 分支。

### 3）ManageOne（新增 1 个对象，minimal）

`manageone_eip`（浮动IP, `list_floating_ips`）。

> **范围说明**：ManageOne 北向 API 的 floating-IP/ELB 系列 formatter 是 **identity 透传**，仅证实 camelCase 键 `id`、`floatingIpAddress`（pool/member 仅 `id/elbId/vmId/poolId`）。故 `manageone_eip` 建为**最小对象**（`resource_id ← id`、`ip_addr ← floatingIpAddress`、`resource_name ← id`），并照现有 `manageone_elb` 的「多键 fallback + log raw sample」防御式风格采集，待真机细化。
>
> **剔除** `manageone_elb_pool` / `manageone_elb_pool_member`：仅证实一个 id + 一个外键，无 grounded 资产字段，本期 defer。

**合计 14 个新子对象模型**（华为云 9 + OpenStack 4 + ManageOne 1）。

> **剔除** `fusioninsight_ds`：驱动 `list_ds` 是 `pass` 空桩，无 API、无字段，无法 grounded，本期不做。FusionInsight 本期不新增对象。

### 4）关联设计（源恒为新对象）

- 华为云：`evs/obs/vpc/eip/sg/elb/rds/dcs belong hwcloud`；`subnet belong hwcloud_vpc`（键 raw vpc_id → 归一化 `vpc`）；驱动确含挂载字段时追加 `evs install_on hwcloud_ecs`（键 `server_id`，来自 attachments[0]）。EIP 真正绑定在 `extra.port_id`（`instance_id` 是空占位），无稳定 EIP→ECS 直连键，故 EIP 仅 `belong hwcloud`。
- OpenStack：`subnet belong openstack_vpc`（键 raw `network_id` → 归一化 `vpc`）；`vpc/eip/sg belong openstack`。（Neutron EIP/SG 的实例/VPC 外键在归一化层被置空，故只 belong 平台。）
- ManageOne：`manageone_eip belong manageone_cloud`（单云回退，沿用现有 `_belong_cloud` 套路）。

挂到存量对象的 `install_on` 仅在驱动返回里确有该挂载字段时建立；查不到则只 `belong` 平台。

## 适用范围

CMDB 自动发现 → 配置采集。用户在已有的华为云/OpenStack/ManageOne 采集任务入口（按平台 model_id 建任务）下，一次采集即拉回平台及其下全部新老子对象并自动建关联。

## 约束与边界

### In Scope（本期）

- 3 平台共 14 个新子对象的：模型定义（`model_config.xlsx` 新增 `models` 条目 + `attr-<model>` + `asso-<model>`，classifications 已存在不增）、stargazer 采集器新增分支、server `collect_plugin` + `community/cloud` 插件新增映射、测试。
- 华为云驱动新增 `list_rds`/`list_dcs` 两个方法（官方 API，字段不杜撰）。
- OpenStack 采集器新增 Neutron REST 分支（VPC/子网/EIP/安全组）。
- COLLECT_OBJ_TREE 华为云条目 `desc` 文案可选更新（"ECS、EVS、VPC、ELB、RDS 等"），纯 UI 描述、非逻辑。

### Out of Scope（本期不做）

- **不改任何存量对象**（模型 + 采集逻辑 + 关联）。
- **不做 SmartX 扩充**（驱动已全覆盖，无新增空间，除非新增驱动方法）。
- **`fusioninsight_ds`**：驱动 `list_ds` 为 `pass` 空桩、无 API、无字段，剔除；FusionInsight 本期不新增对象。
- **`manageone_elb_pool` / `manageone_elb_pool_member`**：formatter 为 identity 透传、仅证实 id+外键、无 grounded 资产字段，defer。
- 华为 RDS/DCS 之外，**不新增其它需要新造驱动方法的对象**；官方文档查不到列实例 API/字段的对象本期不做。
- COLLECT_OBJ_TREE 不新增树入口、不把子对象单列为独立采集项（子对象随平台一次采集拉回）。
- 不做指标监控/告警，不新增凭据体系，不改前端代码（模型页按定义动态渲染；缺 i18n key 时补 cmdb locales）。

## 实施分相

每相为一个独立可审查单元，内部固定四步：①`model_config.xlsx` 加模型（models / attr-* / asso-*）→ ②stargazer 采集器 `list_all_resources` 加新分支（存量分支不碰）→ ③server `collect_plugin` + `community/cloud` 插件追加 `metric_names`/`field_mappings`（含 `MODEL_ORDER` 父在子前 + 累加器映射，照 vmware/manageone 套路）→ ④测试。

- **Phase A — 华为云**（9 对象：evs/obs/vpc/subnet/eip/sg/elb 用现成归一化驱动方法 + rds/dcs 新增驱动方法，作富模板范式）
- **Phase B — OpenStack**（4 网络对象，采集器新增 Neutron REST 三段式分支）
- **Phase C — ManageOne**（manageone_eip 1 个，防御式采集）

全程不 commit，由用户提交。

## 验证策略（单测 + Mock + 字段对照，无真机）

- **stargazer**：mock 驱动返回 fixture，断言 `list_all_resources()` 新对象结构/字段齐全；并加快照断言**守护存量对象输出零变化**。
- **server**：mock VictoriaMetrics 查询返回 `<model>_info_gauge` 向量，断言新对象实例字段逐项匹配新建 `attr-<model>` 列、关联匹配 `asso-<model>`。
- **字段类型对照**：扩展现有 `tests/test_collection_field_type_alignment.py`，读 xlsx `attr_type` 自动校验新对象产出类型（int/str/time），防回归。
- **回归**：跑既有全套，确保存量测试全绿、存量对象采集零变化。
- 真实云端点联调由用户在自有环境完成。

## 验收标准

- 3 平台共 14 个新子对象均可随对应平台采集任务一次拉回，实例按模型字段填充，**无缺漏、无错位、单位/类型正确**。
- 子对象按 `asso-<model>` 自动建关联（belong 平台 / 父子 / 有挂载字段时的 install_on）。
- 实例正确回填 `是否自动采集/采集时间/采集任务`。
- 存量对象（ecs/vm/server/host/cluster/elb/vg/sp 等）的模型与采集结果**完全不变**（回归用例守护）。
- 华为 RDS/DCS 字段与官方 ListInstances 响应一致，无杜撰字段。

## 关联文档

- 前序需求：[20260608.配置采集新增达梦KeepAlive及私有云平台.md](20260608.配置采集新增达梦KeepAlive及私有云平台.md)
- 前序设计：[2026-06-11-cmdb-collection-six-plugins-design.md](../../../docs/superpowers/specs/2026-06-11-cmdb-collection-six-plugins-design.md)
- 华为云 RDS ListInstances：https://support.huaweicloud.com/api-rds/rds_01_0004.html
- 华为云 DCS API：https://support.huaweicloud.com/api-dcs/dcs-api-0514011.html
