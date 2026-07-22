# 技术方案：新增存储设备、InfluxDB、MinIO 配置采集

Status: cancelled

> Migrated from `spec/tech_plan/CMDB/20260615.新增存储设备InfluxDB及MinIO配置采集.md` as historical change evidence.

> 日期：2026-06-15　模块：CMDB　对应需求：`spec/requirements/CMDB/20260615.新增存储设备InfluxDB及MinIO配置采集.md`

## 1. 技术目标与非目标
- **目标**：新增 6 个模型（storage / storage_pool / storage_disk / storage_volume / influxdb / minio）及对应采集；存储采集复用监控侧 OceanStor REST 逻辑，仅取配置（不取性能）。
- **非目标**：存储 SNMP 通用采集、非华为存储、OceanStor NAS/Pacific、性能指标、容器内 MinIO。

## 2. 现状核对
- model_config（`server/apps/cmdb/support-files/model_config.xlsx`）中 storage/influxdb/minio **均不存在**，需新建。
- 监控侧已存在华为采集器：`agents/stargazer/common/monitor_plugins/oceanstor/api.py`（SAN）、`oceanstornas`、`oceanstorpacificanas`；入口 `agents/stargazer/tasks/collectors/oceanstor_collector.py`。CMDB 复用其 REST 登录/分页逻辑。
- 已比对华为官方《OceanStor Dorado 6.1.8 REST 接口参考》PDF，确认调用契约与字段，**作为字段权威来源**。

## 3. 模型与字段口径

### 3.1 命名/类型对齐规则（已核对内置）
- attr_type 仅用 `ATTR_TYPE_MAP` 内类型（str/int/enum/bool/time/user/pwd/organization/table/tag）——**无 float**，容量用 int、单位入中文名。
- 分类 id 用内置原值：`harware`（硬件设备，注意内置拼写）、`hardware_components`（硬件组件层）、`database`、`middleware`。
- 撞名规避：`disk` 已被内置"服务器磁盘"占用，存储子对象统一加 `storage_` 前缀。
- 父子归属用 `self_device`(str)；硬件类对齐 physcial_server/服务器磁盘，库类对齐 mysql/nginx。
- 枚举复用公共库：`brand→vendor`、`asset_status→asset_status`、`running_status→opera_status`；不新建公共库，不足才补选项。

### 3.2 `storage` 存储设备（分类 harware，四组）
| attr_id | 中文名 | attr_type | 唯一 | 分组 | 说明 |
|---|---|---|---|---|---|
| inst_name | 实例名 | str | ✓ | 基本信息 | 必填 |
| organization | 组织 | organization | | 基本信息 | |
| ip_addr | 管理IP | str | | 基本信息 | ipv4 |
| port | 管理端口 | str | | 基本信息 | 华为 8088 |
| device_sn | 设备序列号 | str | ✓ | 基本信息 | 抽象自 device_id |
| asset_code | 资产编号 | str | | 基本信息 | |
| model | 型号 | str | | 基本信息 | Dorado 5000 V6 |
| brand | 厂商 | enum | | 基本信息 | 公共库 `vendor` |
| storage_type | 存储类型 | enum(custom) | | 基本信息 | SAN/NAS/统一/对象/分布式 |
| firmware_version | 微码版本 | str | | 基本信息 | |
| sys_desc | 系统描述 | str | | 基本信息 | 多行 |
| comment | 备注 | str | | 基本信息 | |
| total_capacity | 总容量（GB） | int | | 技术信息 | |
| used_capacity | 已用容量（GB） | int | | 技术信息 | |
| available_capacity | 可用容量（GB） | int | | 技术信息 | |
| pool_count | 存储池数量 | int | | 技术信息 | |
| disk_count | 磁盘数量 | int | | 技术信息 | |
| volume_count | 卷数量 | int | | 技术信息 | |
| running_status | 运行状态 | enum | | 技术信息 | 公共库 `opera_status` |
| operator | 主要维护人 | user | | 管理信息 | |
| bak_operator | 备份维护人 | user | | 管理信息 | |
| cabinet | 所属机柜 | str | | 管理信息 | |
| room | 所属机房 | str | | 管理信息 | |
| asset_status | 资产状态 | enum | | 管理信息 | 公共库 `asset_status` |
| auto_collect / collect_time / collect_task | 自动发现三件套 | bool/time/str | | 自动发现信息 | |

### 3.3 子对象（分类 hardware_components，三组）
> inst_name 统一拼接 **`{所属存储名}/{原生名}`** 防冲突；`self_device` 存所属存储名；OceanStor 字段已照 PDF 锁定。

**storage_pool 存储池**（GET `/storagepool` TYPE=216，PDF p1419-1423）
| attr_id | 中文名 | attr_type | 唯一 | 分组 | OceanStor 字段 |
|---|---|---|---|---|---|
| inst_name | 实例名 | str | ✓ | 基本信息 | `{存储名}/`+`NAME` |
| organization | 组织 | organization | | 基本信息 | |
| self_device | 所属设备 | str | | 基本信息 | 所属 storage |
| pool_type | 池类型 | str | | 技术信息 | `USAGETYPE`（渐废，留空可接受） |
| total_capacity | 总容量（GB） | int | | 技术信息 | `USERTOTALCAPACITY`×SECTORSIZE→GB |
| used_capacity | 已用容量（GB） | int | | 技术信息 | `USERCONSUMEDCAPACITY` |
| available_capacity | 可用容量（GB） | int | | 技术信息 | `USERFREECAPACITY` |
| running_status | 运行状态 | enum | | 技术信息 | `RUNNINGSTATUS`+`HEALTHSTATUS`→`opera_status` |
| auto_collect / collect_time / collect_task | | bool/time/str | | 自动发现信息 | |

**storage_disk 存储磁盘**（GET `/disk` TYPE=10，PDF p657-661；命名对齐内置服务器磁盘）
| attr_id | 中文名 | attr_type | 唯一 | 分组 | OceanStor 字段 |
|---|---|---|---|---|---|
| inst_name | 实例名 | str | ✓ | 基本信息 | `{存储名}/`+`LOCATION`\|`MODEL` |
| organization | 组织 | organization | | 基本信息 | |
| self_device | 所属设备 | str | | 基本信息 | 所属 storage |
| slot | 槽位 | str | | 技术信息 | `LOCATION` |
| disk_vendor | 磁盘厂商 | str | | 技术信息 | `MANUFACTURER` |
| disk_model | 磁盘型号 | str | | 技术信息 | `MODEL` |
| disk_type | 磁盘类型 | str | | 技术信息 | `DISKTYPE`→SSD/SAS/SATA/NL-SAS |
| disk_capacity | 容量（GB） | int | | 技术信息 | `SECTORS`×`SECTORSIZE`→GB |
| disk_sn | 磁盘序列号 | str | | 技术信息 | `SERIALNUMBER` |
| rotate_speed | 转速（RPM） | int | | 技术信息 | `SPEEDRPM`（SSD 为 0） |
| firmware_version | 固件版本 | str | | 技术信息 | PDF disk 固件字段（编码确认） |
| running_status | 运行状态 | enum | | 技术信息 | `RUNNINGSTATUS`(27在线)+`HEALTHSTATUS`(1正常/2故障)→`opera_status` |
| auto_collect / collect_time / collect_task | | bool/time/str | | 自动发现信息 | |

**storage_volume 存储卷/LUN**（GET `/lun` TYPE=11，PDF p1073-1085）
| attr_id | 中文名 | attr_type | 唯一 | 分组 | OceanStor 字段 |
|---|---|---|---|---|---|
| inst_name | 实例名 | str | ✓ | 基本信息 | `{存储名}/`+`NAME` |
| organization | 组织 | organization | | 基本信息 | |
| self_device | 所属设备 | str | | 基本信息 | 所属 storage |
| parent_pool | 所属存储池 | str | | 基本信息 | `PARENTNAME`/`PARENTID`（+建 belong 关联） |
| wwn | WWN | str | | 技术信息 | `WWN` |
| volume_capacity | 容量（GB） | int | | 技术信息 | `CAPACITY`→GB |
| alloc_capacity | 已分配容量（GB） | int | | 技术信息 | `ALLOCCAPACITY` |
| alloc_type | 空间分配方式 | str | | 技术信息 | `ALLOCTYPE` |
| running_status | 运行状态 | enum | | 技术信息 | `RUNNINGSTATUS`+`HEALTHSTATUS`→`opera_status` |
| auto_collect / collect_time / collect_task | | bool/time/str | | 自动发现信息 | |

关联：`storage --contains--> {pool,disk,volume}`、`storage_volume --belong--> storage_pool`。

### 3.4 `influxdb`（分类 database，对齐 mysql，字段以 str 为主）
inst_name(str✓)、organization(org)、ip_addr(str IP)、port(str)｜version、data_dir、wal_dir、meta_dir、engine、http_bind_address、auth_enabled、https_enabled、max_concurrent_queries（均 str）｜operator/bak_operator(user)｜auto_collect(bool)/collect_time(time)/collect_task(str)。

### 3.5 `minio`（分类 middleware，对齐 nginx/kafka，字段全 str）
inst_name(str✓)、organization(org)、ip_addr(str IP)、port(str API 9000)｜version、bin_path、data_path、conf_path、console_port、deploy_mode、region、start_args（均 str）｜operator/bak_operator(user)｜auto_collect(bool)/collect_time(time)/collect_task(str)。

## 4. 接口/采集口径

### 4.1 华为存储（REST，复用监控逻辑）
- 登录 `POST /deviceManager/rest/xxxxx/sessions`（`scope:"0"`）→ 取 `iBaseToken`+`deviceid`；后续 URL 用 deviceid；头 `iBaseToken`；分页 `range=[start-end]`；登出 DELETE `/sessions`。
- 配置端点：`GET /storagepool`、`GET /disk`、`GET /lun`（**仅取配置，不调性能端点**）。
- 状态码归一化：HEALTHSTATUS(1正常/2故障)、RUNNINGSTATUS(27在线…) → 统一映射到 `opera_status`。
- 容量归一化：uint64 扇区 × SECTORSIZE → 字节 → GB/TB（int）。

### 4.2 InfluxDB（协议）采集可行性
| 字段 | 2.x | 1.x | 来源 |
|---|---|---|---|
| version | ✅ | ✅ | `/health` / `/ping` 头 |
| data_dir/meta_dir/engine/http_bind/max_concurrent | ✅ | ⚠️弱 | 2.x `GET /api/v2/config`（需 operator token）；1.x 无 API，留空 |
| wal_dir | ➖ | ⚠️ | 2.x 并入 engine |
| auth_enabled | ✅(恒true) | ⚠️ | |
| https_enabled | ✅ | ✅ | scheme 推断 |
- 结论：**2.x 协议可行字段较全（需 operator token）；1.x 仅稳采 version，路径字段留空**。取不到留空不报错。

### 4.3 MinIO（脚本）采集可行性
脚本 SSH 读进程/环境/配置：version(`minio --version`)、bin_path、port/console_port(`--address`/`--console-address`)、data_path(`MINIO_VOLUMES`)、conf_path(`/etc/default/minio`)、deploy_mode(由 VOLUMES 推断)、start_args(ps)、region(`MINIO_REGION`，未设留空)。**容器化运行为已知限制**（二期处理）。

## 5. 影响范围与改动点

### 5.1 存储（华为 OceanStor）
- `model_config.xlsx`：models 加 storage/storage_pool/storage_disk/storage_volume 四行 + 四张 attr-* + `asso-storage`、`asso-storage_volume`。
- `agents/stargazer/plugins/inputs/oceanstor/`：`__init__.py`、`oceanstor_info.py`（复用监控登录/分页，只取 config）、`plugin.yml`。
- `server/apps/cmdb/collection/plugins/community/storage/oceanstor.py` + `storage/__init__.py`。
- `server/apps/cmdb/constants/constants.py`：`CollectPluginTypes` 加 `STORAGE` + `COLLECT_OBJ_TREE` 加"存储设备"分组与条目（type=API/REST，encrypted_fields=["password"]）。

### 5.2 InfluxDB
- `model_config.xlsx`：models 加 influxdb + attr-influxdb。
- `agents/stargazer/plugins/inputs/influxdb/`：`__init__.py`、`influxdb_info.py`、`plugin.yml`（protocol executor）。
- `server/apps/cmdb/collection/plugins/community/protocol/influxdb.py` + `protocol/__init__.py`。
- `constants.py`：COLLECT_OBJ_TREE databases 加条目（task_type=PROTOCOL，tag=["Agentless","HTTP"]，encrypted_fields=["password","token"]）。

### 5.3 MinIO
- `model_config.xlsx`：models 加 minio + attr-minio。
- `agents/stargazer/plugins/inputs/minio/`：`__init__.py`、`minio_default_discover.sh`、`plugin.yml`（job executor）。
- `server/apps/cmdb/collection/plugins/community/middleware/minio.py` + `middleware/__init__.py`。
- `constants.py`：COLLECT_OBJ_TREE middleware 加条目（task_type=MIDDLEWARE，type=JOB）。

### 5.4 公共库
- 如 `opera_status` 缺"故障/离线"语义，给该公共库**补选项**（不新建库），待真实 config 状态码确认后决定。

## 6. 测试方案
- 模型：`model_init` 导入后校验 6 模型存在、分类/字段/分组正确、子对象关联正确。
- 采集插件单测（`_pure`，参考 testing-guide）：用监控真实采集数据 + PDF 字段构造 JSON 输入，验证 field_mapping、容量归一化、状态码归一化、inst_name 拼接（含父存储名）。
- InfluxDB：2.x/1.x 分别验证（2.x 全字段、1.x version + 留空字段）。
- MinIO：脚本输出 JSON → 映射断言。
- 回归：插件自动注册不影响既有采集（registry 优先级、loader 扫描）。

## 7. 发布与回滚
- 发布：先合模型（model_config + model_init），再合采集插件与 stargazer 采集器。
- 回滚：新模型/插件为增量，回滚即移除新增条目与文件；COLLECT_OBJ_TREE 与 `__init__.py` 注册项可独立摘除，不影响存量模型与采集。

## 8. 实施顺序
1. **MinIO**（脚本，最简单，先跑通采集闭环）。
2. **InfluxDB**（协议，复用 MySQL 模板）。
3. **存储**（通用模型+子对象+华为 REST 采集器，最复杂）。
