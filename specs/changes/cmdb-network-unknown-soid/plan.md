# 网络采集未知 SOID 确认 Implementation Plan

> **For agentic workers:** 按任务顺序 TDD 实现；规格见 `specs/changes/cmdb-network-unknown-soid/spec.md`。

**Goal:** 网络采集对特征库未命中的 sysObjectID 不入库。管理员勾选设备后，可按 SOID 去重批量补映射，再把勾选设备写入四类模型之一，并带上映射里的品牌和型号，不重新采集。

**Architecture:** 未命中只在 `CollectNetworkMetrics.resolve_oid_mapping` 落到合成默认映射时成立。这些设备和接口留在插件实例的未识别分组里，不进入 `result`。分组随 `format_data["unresolved"]` 存在任务最新结果上。界面有两个动作：补全映射只写 `OidMapping`；写入模型只处理勾选设备，类型、品牌和型号取特征库当前行，用本次快照调用 `Management.controller()`。不重放拓扑，不改扫描。

**Tech Stack:** Django ORM、现有 CMDB `Management` / `MetricsCannula`、DRF、Next.js、Ant Design。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `server/apps/cmdb/collection/collect_plugin/network.py` | 识别合成默认映射；未识别设备/接口不进 `result`；拓扑丢掉未识别端点 |
| `server/apps/cmdb/collection/collect_tasks/base.py` | 把插件上的未识别分组抄进 `format_data["unresolved"]` |
| `server/apps/cmdb/models/collect_model.py` | `info` 带出 `unresolved` |
| `server/apps/cmdb/services/network_unknown_soid.py` | 校验终态、写特征库、入库、摘掉该组 |
| `server/apps/cmdb/views/collect.py` | `confirm_unknown_soid` |
| `server/apps/cmdb/support-files/plugins_doc/network.md` | 去掉「未知当交换机」的说明 |
| `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/taskDetail.tsx` | 未识别分组和确认弹窗 |
| `web/src/app/cmdb/api` 里现有采集客户端 | 确认请求 |
| `web/src/app/cmdb/locales/{zh,en}.json` | 文案 |

不新建表。`CollectModels.format_data` 已是 JSON。不改 `scan_identity.py`、`OidMapping` 模型、`ALLOWED_DEVICE_TYPES`。

---

## 数据流

1. `format_data` 遇到带 `sysobjectid` 的设备指标时仍调用 `resolve_oid_mapping`。
2. 返回值来自精确命中或不少于 7 段的前缀命中：照旧写入 `result[device_type]`，接口和拓扑不变。特征库行的型号文本即使是「未知」，只要 `device_type` 是四类之一，也算命中。
3. 返回值是 `get_default_oid_map` 的合成结果：不写入 `result`。按规范化后的 SOID 归入插件属性 `unresolved_groups`。同组保存每台设备的 `ip_addr`、`port`、`sys_desc`，以及该设备接口的 `name`、`description`、`mac`、`status`。没有 `sysobjectid` 的行继续丢弃，不进未识别。
4. 拓扑关系在写入前丢掉源或目的设备属于未识别 IP 的链路。已识别设备之间的链路照旧。
5. `BaseCollectTask.format_collect_data` 结束后，若插件实例有 `unresolved_groups`，写入 `format_data["unresolved"]`。这个键不是模型 ID，`MetricsCannula._collect_models` 不会遍历它。Celery 仍把整份 `format_data` 存到任务上；下一次成功采集整份覆盖，未确认分组自然消失。
6. 任务 `info` 增加 `unresolved: {data, count}`。`count` 是设备台数，不是组数。

`unresolved` 组的形状：

```python
{
    "soid": "1.3.6.1.4.1.99999.1",
    "devices": [
        {
            "ip_addr": "10.0.0.8",
            "port": "",
            "sys_desc": "Example firewall",
            "interfaces": [
                {"name": "GigabitEthernet0/1", "description": "", "mac": "", "status": "UP"}
            ],
        }
    ],
}
```

确认时再计算实例名，不把 `{ip}-switch` 存进快照。

```python
inst_name = f"{ip_addr}-{device_type}"
interface_inst_name = f"{inst_name}-{interface_name}"
```

接口关联为 `interface_belong_{device_type}`，指向该设备实例名。

---

## 交互

未识别是一张可勾选的设备表，不是一 SOID 一个弹窗。两个按钮都要求已勾选，且任务已成功或部分成功。

勾选的设备按规范化 SOID 去重。表的一行是一个 SOID，列是 SOID、勾选台数、设备类型、品牌、型号。SOID 不可编辑。设备类型只有交换机、路由器、防火墙、负载均衡。

- **补全映射**：已有特征库行的 SOID 预填并锁定。空行必填类型、品牌、型号。提交只创建缺失的非内置 `OidMapping`，不写实例。列表刷新后，这些设备显示映射上的类型、品牌和型号，仍可再勾选写入。
- **写入模型**：每个勾选 SOID 都已有映射时，表只读，确认后写入。还有空映射时，先在同一张表里补完，保存映射，再写入。写入只包含勾选的 IP 及其接口。类型、品牌、型号取特征库当前行，字段来自本次快照里的 `ip_addr`、`port`、`sys_desc` 和接口，不重新采集。未勾选的同 SOID 设备留在未识别里。

## 两个动作

权限仍是并且关系：视图用 `auto_collection-Execute`，服务再拒绝没有 `soid_library-Add` 的用户，并沿用 `exec_task` 的任务组织校验。`HasPermission` 的逗号分隔是或，不能用来同时要求两项。

两个接口都拒绝：任务不是 `network`；状态不是成功或部分成功；SOID 不在当前未识别结果里；品牌或型号为空；设备类型不是四类之一。

`POST /cmdb/api/collect/{task_id}/unknown_soid_mappings/`

请求体：`items: [{soid, device_type, brand, model}]`。只写特征库。OID 已存在则跳过且不修改。响应返回每行实际采用的类型、品牌、型号，以及 `created` / `skipped`。不改 `format_data`。

`POST /cmdb/api/collect/{task_id}/write_unknown_devices/`

请求体：`ip_addrs: [string]`。这些 IP 必须属于当前未识别设备。任一 SOID 没有特征库行则整批拒绝，并返回缺少映射的 SOID，不写实例。通过后按映射的 `device_type` 分组，用任务 `team` 和任务 ID，`manual=False`，调用与 `MetricsCannula` 相同的 `Management.controller()`。设备行的 `brand`、`model`、`soid` 用特征库行，不用快照里的「未知」。先写设备，再写接口和 `interface_belong_{device_type}`。成功后只从 `unresolved` 删除这些 IP；组里还有设备则保留该组。不改 `topology_snapshot`。

映射保存和写入分开提交。写入失败时，已经创建的特征库行保留，设备仍在未识别里，用户可以再写入。

历史 `{ip}-switch` 不删除。映射类型仍是交换机时，实例名与旧脏数据相同，现有按 `inst_name` 对账会更新那条。其他类型留下旧交换机，本变更不迁移。

---

### Task 1: 采集不再把未命中 SOID 写成交换机

- Modify: `server/apps/cmdb/collection/collect_plugin/network.py`
- Modify: `server/apps/cmdb/collection/collect_tasks/base.py`
- Modify: `server/apps/cmdb/support-files/plugins_doc/network.md`
- Test: `server/apps/cmdb/tests/test_network_device_field_mapping_pure.py`

- [ ] 合成默认映射与前缀命中可区分。前缀行型号为「未知」但类型是防火墙时，仍进 `result["firewall"]`。
- [ ] 合成默认映射的设备不出现在 `result["switch"]`，接口不出现在 `result["interface"]`，二者进入 `unresolved_groups`。
- [ ] 以未识别 IP 为端点的拓扑链路不进入关系列表。
- [ ] `format_collect_data` 的返回值含 `unresolved`，且 `add` 里没有这些设备。
- [ ] `network.md` 改为：未命中 SOID 不入库，等任务结果里确认后再写入特征库和对应模型。同步改测试里的旧文案断言。
- [ ] `get_default_oid_map` 的字典形状保持不变，避免扫描和目录测试跟着改语义。扫描 `refine_scan_metrics` 不改。

### Task 2: 任务详情露出未识别

- Modify: `server/apps/cmdb/models/collect_model.py`
- Test: `server/apps/cmdb/tests/test_models.py`

- [ ] `info["unresolved"]` 为 `{"data": groups, "count": device_count}`。没有该键时是空列表、台数 0。
- [ ] 现有 add / update / delete / relation 计数不变。

### Task 3: 补映射与写入

- Create: `server/apps/cmdb/services/network_unknown_soid.py`
- Modify: `server/apps/cmdb/views/collect.py`
- Test: `server/apps/cmdb/tests/test_network_unknown_soid.py`、`server/apps/cmdb/tests/test_collect_views_actions.py`

- [ ] 补映射：两个相同 SOID 只创建一行非内置 `OidMapping`；不调用 `Management.controller`；`unresolved` 仍在。
- [ ] OID 已存在时不新建、不修改。写入使用库里的类型、品牌、型号，设备行上的品牌和型号不是「未知」。
- [ ] 写入只删除请求中的 IP。同 SOID 的另一台未请求设备仍留在 `unresolved`。
- [ ] 任一勾选 SOID 没有映射时整批拒绝，响应带上这些 SOID，且没有实例写入。
- [ ] 非终态、非 network 任务、空品牌、非法类型、缺少 `soid_library-Add` 均拒绝。
- [ ] 视图权限装饰是 `auto_collection-Execute`，并做任务组织校验。

### Task 4: 去重表格

- Modify: `taskDetail.tsx`、采集 API 客户端、`web/src/app/cmdb/locales/zh.json`、`en.json`
- Test: 去重纯函数放在采集组件旁的 `unknownSoidRows.ts`，并用 vitest 锁定

- [ ] 未识别是可勾选设备表。已有映射的行展示类型、品牌、型号。未勾选时两个按钮禁用。
- [ ] `uniqueSoidRows(selectedDevices)` 按 SOID 合成一行，并带上勾选台数。相同 SOID 不出现第二行。
- [ ] 「补全映射」打开这张表。已有映射的行锁定。提交后不写入模型，刷新后设备仍在，并显示品牌和型号。
- [ ] 「写入模型」在仍有空映射时打开同一张表，先保存映射再写入勾选设备。全部已有映射时表只读，确认后写入。成功后这些 IP 从列表消失。
- [ ] 执行中、未开始、写入中禁用两个按钮。
- [ ] 文案说明：补映射不会入库；写入使用已填的厂商和型号，不需要重新采集。

### Task 5: 验证

```
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/cmdb/tests/test_network_device_field_mapping_pure.py apps/cmdb/tests/test_network_unknown_soid.py apps/cmdb/tests/test_models.py apps/cmdb/tests/test_collect_views_actions.py apps/cmdb/tests/test_oid_catalog.py apps/cmdb/tests/test_scan_identity.py --no-cov
cd web && pnpm exec vitest run src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/__tests__ && pnpm type-check
```

`test_scan_identity.py` 只作回归，确认扫描仍不把未知 SOID 建成交换机。前端没有现成任务详情测试时，类型检查覆盖新增字段；不补 Playwright。
