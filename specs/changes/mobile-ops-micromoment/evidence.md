# Mobile 运维微场景 MVP 事实核验

## 核验范围

本文件记录实施前从当前 Web、Server 和 Mobile 代码得到的事实。只记录接口与行为，不包含凭据或生产数据。核验日期：2026-08-03。

## 许可与菜单权限

| 事实 | 证据 | 结论 |
|---|---|---|
| 应用可见列表 | `GET /core/api/get_client/`；`server/apps/core/views/index_view.py::get_client` | 返回当前账号有角色的应用；企业实现随后按 license 过滤。Mobile 可直接复用最终结果。 |
| 企业许可过滤 | `enterprise/server/apps/core/enterprise/license_filter.py::filter_clients_by_license` | 内置应用按有效许可过滤；非内置应用和许可白名单按 Web 当前规则保留。Mobile 不解析许可记录。 |
| 静态菜单树 | Web `GET /api/menu?locale=...`；`web/src/app/(core)/api/menu/route.ts` | 这是 Web Next 路由，不是 Django 路由。Mobile H5/Tauri 若复用，必须明确代理到 Web，不能请求 Server `/api/proxy`。 |
| 用户菜单 | `GET /core/api/get_user_menus/?name=<client>`；`RoleManage.get_all_menus` | 返回按资源名聚合的 operation 树；超级管理员和应用管理员规则由 Server 处理。 |
| 自定义菜单 | `GET /system_mgmt/custom_menu_group/get_menus/?app=<client>` | 404 表示无启用菜单组，Web 回退静态菜单；`is_build_in=false` 时使用返回菜单树。 |
| Web 解析语义 | `web/src/context/permissions.tsx` | 包含目录过滤、`isNotMenuItem`、`withParentPermission`、operation 提取和路由 client 过滤。 |

### Mobile 固定映射

| Mobile 模块 | client | 菜单资源 | Server 菜单证据 |
|---|---|---|---|
| 待办 | `alarm` | `Alarms-View`；操作为 `Alarms-Edit` | `server/support-files/system_mgmt/menus/alarm.json` |
| 监控 | `monitor` | `view_list-View` | `server/support-files/system_mgmt/menus/monitor.json` |
| 资产 | `cmdb` | `asset_info-View`；全局搜索为 `search-View` | `server/support-files/system_mgmt/menus/cmdb.json` |
| 智能应用 | `opspilot` | `bot_list-View` | `server/support-files/system_mgmt/menus/opspilot.json` |
| 我的 | 登录 | 无业务菜单要求 | Mobile 基础入口 |

## 待办 / 告警

| 能力 | 接口与证据 | 权限/状态结论 |
|---|---|---|
| 列表 | `GET /alerts/api/alerts/`；`AlertModelViewSet.list` | `Alarms-View`；默认「当前组织 ∪ 处理人是我」，`org_only` 时只按组织。 |
| 我的告警 | 参数 `my_alert=1/true/yes` | 按当前处理人精确成员匹配，跨组织汇总；组织列表仍只看归属。 |
| 未关闭 | 参数 `activate=<非空值>`，或 `status=unassigned,pending,processing` | `AlertStatus.ACTIVATE_STATUS` 与已确认三状态一致。 |
| 高优先级 | 列表支持 `level=<逗号分隔>` | 级别列表 `GET /alerts/api/level/?type=alert` 按 `level_id` 排序，但接口需要 `global_config-View`。见确认项 A。 |
| 标题/内容/ID 搜索 | `title`、`content`、`alert_id` 查询参数 | 当前过滤器直接支持。 |
| 详情 | `GET /alerts/api/alerts/{pk}/` | `Alarms-View`；归属组织成员或当前处理人可进入。 |
| 事件 | `GET /alerts/api/alerts/{pk}/events/` | `Alarms-View`；能看见该告警即可看本条关联事件。 |
| 相关告警 | `GET /alerts/api/alerts/{pk}/related/` | `Alarms-View`，结果受组织范围限制。 |
| 分派 | `POST /alerts/api/alerts/operator/assign/` | `Alarms-Edit`；仅 `unassigned -> pending`，校验有效处理人。 |
| 认领 | `POST /alerts/api/alerts/operator/acknowledge/` | `Alarms-Edit`；仅 `pending -> processing`，当前用户必须在 `operator`。 |
| 转派 | `POST /alerts/api/alerts/operator/reassign/` | `Alarms-Edit`；仅 `processing -> pending`，当前用户必须在 `operator`，校验新处理人。 |
| 关闭 | `POST /alerts/api/alerts/operator/close/` | `Alarms-Edit`；仅 `processing -> closed`，当前用户必须在 `operator`；原因可省略，默认“告警已处理完成”。 |
| 操作记录 | `GET /alerts/api/log/?target_id=<alert_id>` | 现有全局日志接口要求 `operation_log-View`，不是 `Alarms-View`。见确认项 B。 |

## 监控

| 能力 | 当前接口 | 证据 |
|---|---|---|
| 对象与实例数 | `GET /monitor/api/monitor_object/?add_instance_count=true` | `web/src/app/monitor/api/index.ts`；Web 默认过滤 `is_visible=false`。 |
| 对象内实例列表 | `GET /monitor/api/monitor_instance/{objectId}/list/` | objectId 是必需业务范围。 |
| 对象内实例搜索 | `POST /monitor/api/monitor_instance/{objectId}/search/` | `web/src/app/monitor/api/view.ts`，不存在跨对象实例搜索接口。 |
| 有效插件 | `GET /monitor/api/monitor_instance/{objectId}/effective_plugins/?instance_id=...` | 当前对象/实例范围。 |
| 指标与分组 | `/monitor/api/metrics/`、`/monitor/api/metrics_group/` | 由对象和插件元数据驱动。 |
| 当前值与趋势 | `/monitor/api/metrics_instance/query/`、`/monitor/api/metrics_instance/query_range/` | 支持瞬时与区间查询。 |

| 最近查看 | Mobile 本机 `localStorage`（键按账号与团队隔离）；展示时 `resolveRecentViews` 走现有实例 API | `mobile/src/features/monitor/recent-views-storage.ts`；**不写 Server**，不新增 Monitor 表或 `recent_views` API |

**架构约束（2026-08-06 定稿）**：最近查看为 Mobile 本机 localStorage，不跨设备、不写 Server。若需跨端同步或 Web 共用，须单独产品决策后再设计 Server 能力，不得静默复用 CMDB `user_configs` 或补回临时表。

## 资产 / CMDB

| 能力 | 当前接口 | 权限/结论 |
|---|---|---|
| 分类 | `/cmdb/api/classification/` | Web `useClassificationApi`；默认不请求隐藏分类。 |
| 模型 | `/cmdb/api/model/` | Web `useModelApi`；默认不请求隐藏模型。 |
| 模型实例数 | `/cmdb/api/instance/model_inst_count/` | 现有实例接口。 |
| 模型内实例 | `POST /cmdb/api/instance/search/` | `asset_info-View`，服务端数据范围继续生效。 |
| 全文统计 | `POST /cmdb/api/instance/fulltext_search/stats/` | `search-View`。 |
| 按模型全文结果 | `POST /cmdb/api/instance/fulltext_search/by_model/` | `search-View`。 |
| 实例详情 | `GET /cmdb/api/instance/{id}/` | `asset_info-View`。 |
| 字段分组 | `GET /cmdb/api/field_groups/full_info/?model_id=...` | 现有 Web 模型元数据入口。 |
| 关注配置 | `GET /cmdb/api/user_configs/by_key/cmdb_followed_assets/`、`POST /cmdb/api/user_configs/update_key/` | 账号/域隔离的 `UserPersonalConfig`，无需新模型。 |

Web 关注结构由 `web/src/app/cmdb/utils/followedAssets.ts` 定义：`items[{model_id, inst_id, followed_at}]`、最多 100 条、按 `followed_at` 倒序。

## 账号、语言、时区与主题

| 能力 | 当前事实 | 结论 |
|---|---|---|
| 登录信息 | `/core/api/login_info/` | 响应包含当前账号资料；Mobile 当前认证规范化尚未显式保存 `timezone`。 |
| 完整账号信息 | `GET /console_mgmt/get_user_info/` | 返回 display name、email、locale、timezone、组织路径和角色。 |
| 保存资料 | `POST /console_mgmt/update_user_base_info/` | 支持 display name、locale、timezone；邮箱变更另有验证约束。 |
| Mobile 现状 | `mobile/src/app/profile/accountDetails/page.tsx` | 已有语言和时区 Picker，并提交 locale/timezone；产品确认继续保留。 |
| Web 时间 | `web/src/hooks/useLocalizedTime.ts`、`web/src/utils/userPreferences.ts` | 默认时区 `Asia/Shanghai`，使用账号/session 时区格式化。 |
| Mobile 时间 | 会话、搜索和历史中存在设备时区与硬编码 `zh-CN` | 第一阶段需要统一为账号 locale/timezone，避免二次偏移。 |
| 主题 | `mobile/src/context/theme.tsx` | localStorage 本地偏好；继续保留，不写账号服务。 |

## 已确认的现有权限差异

### A. 高优先级所需级别配置权限

`GET /alerts/api/level/?type=alert` 要求 `global_config-View`。普通告警角色的内置权限只有 `Alarms-View` 等，不保证拥有 `global_config-View`，因此“能看待办但无法读取最高两个告警级别”是可能状态。

产品结论：MVP 不新增接口、不放宽权限，Mobile 与 Web 一样调用现有级别接口，由 Server 的 `global_config-View` 最终裁决。403 时不硬编码级别，也不伪造“高优先级”结果；错误限制在该视图并允许重试。

筛选口径：MVP 的“高优先级”只取真实级别配置按 `level_id` 升序的第一个有效等级，不再取前两个等级。

### B. 告警变更记录权限

现有 `/alerts/api/log/` 需要 `operation_log-View`，普通告警查看者不一定具备。它也是系统级操作日志，不是告警详情专属接口。

产品结论：MVP 不新增告警专属时间线接口，Mobile 与 Web 一样调用现有日志接口，由 Server 的 `operation_log-View` 最终裁决。403 时变更记录区显示无权限状态，摘要和事件仍独立可用。

两个权限差异均已于 2026-08-03 确认沿用 Web，阶段 0 不再阻塞待办实现。

## 阶段零结论

- 许可、菜单、账号、监控、CMDB 主路径均有现成事实和接口，不需要新业务模型。
- Mobile 复用 Web 静态菜单需要补齐运行形态代理，但不引入启动期依赖。
- 告警高优先级级别读取与变更记录继续沿用 Web 的现有接口及权限，不新增 Mobile 旁路。
- 当前 Mobile 已有时区设置并获确认保留；后续发现类似“原型未展示但现网已有”的能力，先确认再调整。
