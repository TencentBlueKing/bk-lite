# CMDB 实例 UUID — 前端对接说明（本阶段不改 Web）

Date: 2026-08-10  
Status: frontend implemented on branch `local_codex/cmdb-instance-uuid`（Web 已按下列清单切换 `inst_uuid`）  
后端契约：[spec.md](./spec.md) Q2 / §8  
延期声明：[DEFER.md](./DEFER.md)（历史延期记录；本分支已落地前端）

后端对外已切到 `inst_uuid`。当前 Web 仍大量使用 `_id` / `inst_id`（数字）。  
前端独立变更时按下列清单改路径、请求体与 rowKey；联调前勿对生产单独发后端。

## 1. 身份字段对照

| 场景 | 旧（现状 Web） | 新（后端契约） | 备注 |
|---|---|---|---|
| 列表行主键 / rowKey | `_id` | `inst_uuid` | 响应不再保证 `_id` 作业务键 |
| 详情 URL query | `inst_id=<数字>` | `inst_uuid=<UUIDv4>` | 数字 path/query 将被拒 |
| 批量操作 | `inst_ids: number[]` | `inst_uuids: string[]` | |
| 关联创建 | `src_inst_id` / `dst_inst_id` | `src_inst_uuid` / `dst_inst_uuid` | |
| 关注资产 | `inst_id` | `inst_uuid`（以后端 API 为准） | |
| 订阅规则 filter | `instance_ids` | `instance_uuids` | 写侧已拒纯数字 |
| OpenAPI 路径 | `/instances/<id>` | `/instances/<inst_uuid>` | |
| 运营分析节点 | `bk_inst_id` | `bk_inst_uuid` | OA 后端已改名 |
| Telegraf 监控标签 | `cmdb_{task_id}` | **不变** | 不是实例 UUID |

## 2. 优先改动的页面与组件（路径）

### CMDB 资产

- `web/src/app/cmdb/(pages)/assetData/page.tsx` — 列表跳转、`rowKey="_id"`、关注 `inst_id`
- `web/src/app/cmdb/(pages)/assetData/detail/**` — 几乎所有子页 `searchParams.get('inst_id')`
  - `baseInfo/`、`layout.tsx`、`relationships/*`、`ipView/`、`k8sResources/`、`configFiles/`、`changeRecords/`
- `web/src/app/cmdb/(pages)/assetData/list/fieldModal.tsx` — `inst_ids`
- `web/src/app/cmdb/(pages)/assetData/components/exportModal.tsx` — `inst_ids`
- 拓扑编辑：`relationships/networkTopo/topoEditingUtils.ts`（端口/设备数字 id）

### 订阅

- `web/src/app/cmdb/hooks/useSubscription.ts`
- `web/src/app/cmdb/components/cmdb-subscription-drawer/*`
- `web/src/app/cmdb/components/subscription/*`
- `web/src/app/cmdb/types/subscription.ts` — `instance_ids: number[]` → UUID 字符串数组

### 运营分析网络拓扑

- `web/src/app/ops-analysis/api/networkTopology.ts` — `bk_inst_id`
- `web/src/app/ops-analysis/(pages)/view/networkTopology/**` — `bk_inst_id` 比较与 key

### 采集 / 自动发现 UI（若展示实例目标）

- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/**` — 确认任务目标字段与后端
  `inst_uuid` / `subnet_uuids` 对齐（监控 Telegraf 标签勿改）

## 3. 建议迁移顺序

1. 统一 API client：实例定位只传 `inst_uuid`；列表消费 `inst_uuid` 作 key。  
2. 详情与关系 URL：`inst_id` → `inst_uuid`（可短暂同时读两参数，但写只发 UUID）。  
3. 订阅 / 关注 / 导出 / 批量编辑。  
4. 拓扑与 OA `bk_inst_uuid`。  
5. 清掉对响应 `_id` 的业务依赖；Storybook / 脚本里的数字 fixture 一并替换。

## 4. 验收（前端变更票）

- 数字 `inst_id` URL 打开详情 → 后端 4xx，UI 有明确错误，不静默打到错误实例。  
- UUID URL / 列表进入详情、建关联、订阅、关注全链路成功。  
- 网络拓扑画布节点身份为 `bk_inst_uuid`。  
- 回归：监控集成页的 `cmdb_{task_id}` 展示/配置不被误改成实例 UUID。

## 5. 发布节奏

后端 UUID 与前端数字 **不能** 长期混跑。推荐：同一版本发布；或维护窗口先发后端+清洗，
紧接着发前端。详见 `docs/operations/cmdb-instance-uuid-cutover.md`。
