# 深信服 EDS 存储插件看板适配缺口

审计结论：可以把插件注册到已有监控对象 **Storage**（分类 Hardware Device），侧栏顺序与许可目录已经预留该对象；**不能**把 `sangfor_eds_*` 直接绑到现有专业盘或网络设备卡片上。因此本变更加最小接线，使实例出现在「硬件设备 / 存储」下，并用对象详情卡展示存储指标，不改网络设备盘。

## 能适配的部分

| 位置 | 结论 |
| --- | --- |
| `server/apps/monitor/constants/monitor_object.py` `DEFAULT_OBJ_ORDER` | 已有 `Storage`，归类 `Hardware Device`，位于堡垒机与硬件服务器之间。插件 `name=Storage`、`type=Hardware Device` 即可进入该侧栏。 |
| `server/apps/monitor/constants/license_catalog.py` | 已将 `Storage` 列入计费对象，无需改目录。 |
| 通用指标详情 / 指标浏览器 | 只要 `metrics.json` 注册 `sangfor_eds_*`，实例详情的指标列表可以展示，不依赖专业盘。 |
| 接入表单 | `UI.json` + `usePluginFromJson` 足以渲染 SNMP 表单；不走防火墙 configLoader。 |

## 不能清洁适配的缺口（本次不硬接网络盘）

1. **没有社区存储专业盘**
   - `web/src/app/monitor/dashboards/metadata.ts` 的 `COMMUNITY_DASHBOARD_METADATA` 无 `objectName: Storage`。
   - `web/src/app/monitor/dashboards/component-loaders.ts` 无 `storage` loader。
   - `web/src/app/monitor/dashboards/objects/` 无 storage 目录；现有盘是 host / firewall / minio 等。
   - MinIO 专业盘在中间件分组，卡片绑定的是 `minio_*`，不能复用 `sangfor_eds_*`。
   - 商业 overlay 的 `(enterprise)-metadata.ts` / `(enterprise)-loaders.ts` 由构建生成且不进开源仓，社区无法依赖其中是否已有 OceanStor 盘。

2. **接入 configLoader 原先没有 Storage**
   - `web/src/app/monitor/hooks/integration/configLoaders.ts` 在改动前无 `Storage` 键。
   - `web/src/app/monitor/hooks/integration/objects/hardwareDevice/` 原先只有 `hardware.tsx`、`bastionHost.tsx`。
   - 后果：`getCollectType('Storage', plugin)` 为空；`getDashboardDisplay('Storage')` 为空，对象详情概览卡不会出现。
   - 本次最小补齐：新增 `storage.tsx`，并把 `Storage` 登记到 `configLoaders.ts`，`dashboardDisplay` 只绑 `sangfor_eds_*`。

3. **没有可对照的社区存储 SNMP/HTTP 叶子**
   - `server/apps/monitor/support-files/plugins/` 下无 OceanStor / 浪潮 / 曙光等存储监控插件。
   - 华为 OceanStor 出现在 CMDB / Stargazer 采集（`agents/stargazer/plugins/inputs/oceanstor/`、`server/apps/cmdb/collection/plugins/community/cloud/oceanstor.py`），不是 Monitor Telegraf 指标叶子，指标名也无法给 EDS 复用。

4. **对象详情卡契约按指标名硬编码**
   - `web/src/app/monitor/(pages)/view/detail/overview.tsx` 只渲染 `dashboardDisplay` 里的 `indexId`。
   - 防火墙 / 交换机卡用 `device_cpu_usage`、`interfaces` 等网络语义，不能把 EDS 集群容量塞进去。
   - 本次不改这些网络对象配置。

5. **语言兜底**
   - `server/apps/monitor/language/zh-Hans.yaml` 的 `monitor_object` 未写 `Storage: 存储`。
   - 插件 `language/zh-Hans.yaml` 已提供对象译名；插件初始化后侧栏可显示「存储」。未跑 `plugin_init` 时仍可能看到英文 `Storage`。

## 本次最小落地（不做专业盘）

- 插件目录 `Telegraf/snmp/storage_sangfor_eds`，对象 `Storage` / `Hardware Device`。
- 测量名全部 `sangfor_eds_*`，不使用 `device_*`。
- 接入：`storage.tsx` + `configLoaders.ts` 的 `Storage` 项。
- 专业存储仪表盘（容量环图、池/卷排行等）仍缺，留待后续单独做 `dashboards/objects/storage`。
