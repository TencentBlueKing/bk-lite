# CMDB Redfish P0：部件台账补齐

Status: implemented

正式规格见产品文档《CMDB Redfish P0：部件台账补齐》（2026-09-24）。本变更只做后端模型、Redfish 映射和单测。物理机详情展示属于规格 §6 的前端分工，不在本次改动里。

## 验收（规格 §7）

1. 采集任务类型仍是 `physcial_server` Redfish，不新增并行采集对象。
2. BMC 暴露时入库 `storage_controller`、`psu`，并用 `physcial_server contains` 关联主机。
3. 主机在 BMC 提供时写入 `power_state`、`health`。
4. disk/nic 在有源字段时写出补强项。
5. 没有 Power 或 StorageControllers 时任务成功，只缺对应子对象。
6. 不把温度、电压、风扇转速、瞬时功耗写入 CMDB。

## 字段规则

- `sc_id`：`Id`，否则 `MemberId`。两者都没有则跳过。
- `psu_name`：`Name`，否则 `MemberId` 或 `Id`。
- `health`：只接受 `OK` / `Warning` / `Critical` / `Unknown`。缺省或其他值不写。不用 `HealthRollup`。
- `power_state`：`On` / `Off`（忽略大小写）。其他非空 `PowerState` 原样保留，保证 BMC 有值就能看见。
- `nic_speed_mbps`：优先当前链路（`CurrentLinkSpeedMbps`、`CurrentSpeedMbps`、`SpeedMbps`、`CurrentSpeedGbps`），没有再取最大速率（`MaxSpeedMbps`、`MaxLinkSpeedMbps`、`MaxSpeedGbps`）。
- `nic_iface`：功能 `Name`、适配器 `Name`、功能 `Id`、适配器 `Id`。标准 Redfish 没有操作系统网口名。
- 不写 `PowerInputWatts`、`PowerOutputWatts`、`PowerConsumedWatts` 和电压、温度、转速。
- `Status.State=Absent` 的磁盘、控制器、电源不入库。
