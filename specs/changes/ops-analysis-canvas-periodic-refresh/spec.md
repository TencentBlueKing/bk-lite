# 分析画布周期刷新

Status: done

## Problem Statement

值班和持续观测需要分析画布按可配置间隔自动更新运行态数字。现在仪表盘和大屏只有手动刷新；拓扑图和网络拓扑虽有频率下拉，但每次刷新都会把已有数字换成 loading。挂在墙上的画布会闪，打开一张盘也不会记住上次选的间隔。

## Solution

四种有运行态数据的分析画布（仪表盘、大屏、拓扑图、网络拓扑）统一提供「刷新按钮 + 频率下拉」。频率随画布保存。周期到点时只重拉运行态数据：不出 loading，旧值留着，新值到了再换。手动刷新、首次进入、改筛选或命名空间仍出 loading。

## User Stories

1. 作为运营分析用户，我希望在仪表盘、大屏、拓扑图、网络拓扑的工具栏看到同一组刷新控件（刷新按钮 + 关/1m/5m/10m），从而四种画布手感一致。
2. 作为运营分析用户，我希望有编辑权限时在查看态改频率并当场写入画布，从而下次打开、分享出去、复制或 YAML 导入导出都还是这个间隔。
3. 作为运营分析用户，我希望打开已有画布和新画布时默认频率为「关」，从而不会因为本期落库而突然开始自动刷。
4. 作为值班人员，我希望周期刷新时数字和图表原地更新、不出现 loading，从而挂墙的大屏不会闪。
5. 作为值班人员，我希望点刷新按钮时仍看到 loading，从而知道这次是我触发的重查。
6. 作为值班人员，我希望改统一筛选或命名空间后组件按新条件重查并出 loading，从而不会把旧条件下的数字当成新结果。
7. 作为值班人员，我希望相对时间窗每次按此刻重算、自定义绝对区间保持不动，从而「近 15 分钟」会往前滑。
8. 作为分享链接的查看者，我希望画布按已保存频率自动静默刷新，并能看到刷新控件；我改频率只对这次打开有效，不写回源画布。
9. 作为没有编辑权限的查看者或内置画布使用者，我希望仍按已保存频率自动刷，但我改的频率只对这次打开有效，从而内置同步不会因为我改过频率而出现写不进或写了又丢的错觉。
10. 作为画布编辑者，我希望编辑布局或节点时运行态数字仍在静默更新，但我正在改的草稿和表单不被冲掉。
11. 作为值班人员，我希望某一轮周期刷新失败时仍显示上一轮成功的数字，而不是把组件打成错误态；我手动刷新失败则仍看到现有错误展示。

## Implementation Decisions

- 本期只覆盖仪表盘、大屏、拓扑图、网络拓扑。架构图没有运行态取数，不做周期刷新。报表周期刷新与 YAML `refresh_interval` 由 [`ops-analysis-report-canvas-toolbar`](../ops-analysis-report-canvas-toolbar/spec.md) 覆盖。
- 工具栏统一复用现有时间选择器的「仅刷新」形态：左边手动刷新，右边频率。档位固定为关 / 1m / 5m / 10m，不新增 30 秒或其他自定义秒数。仪表盘、大屏用这组控件替换现在的单独刷新图标。
- 频率是画布级运行设置，不是组件配置，也不进布局 JSON。四种画布都用同一字段 `refresh_interval`。
- `refresh_interval` 存毫秒，合法值只有：

```ts
type CanvasRefreshIntervalMs = 0 | 60000 | 300000 | 600000;
```

`0` 表示关。详情、更新、分享和 YAML 都用这组值。非法值拒绝写入，读取到非法或缺省时按 `0` 展示。
- 网络拓扑已有同名字段，当前是「秒、默认 60」，且从未接到界面。本期把它改成上述毫秒语义，存量行一律写成 `0`。不要把旧的 `60` 解释成 60ms 或 1 分钟。
- 运行时区分两个间隔，定时器只认 **effective**：
  - `savedRefreshInterval`：服务端画布字段，打开画布时读入
  - `effectiveRefreshInterval`：当前页实际用于下拉展示和 `setInterval` 的值
  有 `view-EditChart` 且非内置时，两者在 PATCH 成功后对齐；无权限、分享、内置画布改下拉只改 effective，不写 saved。分享页/session override 之后不得继续用 saved 值开定时器。
- 新画布默认 `0`。有 `view-EditChart`、且画布非内置时，改频率（查看态和编辑态相同）只 field-scoped PATCH 该字段，不进入布局/组件草稿，不等「保存画布」。允许 optimistic UI：PATCH 成功后新值成为 saved baseline，并写回客户端 canonical 画布状态；PATCH 失败则 UI 与 effective interval 都回退到最后一次成功保存值，并提示失败。
- 四种画布工具栏在编辑态也展示同一组刷新控件（仪表盘/大屏现有刷新按钮、拓扑图/网络拓扑的 `TimeSelector` 均未被编辑态藏掉）。编辑器的取消/保存不得回滚或覆盖已经 PATCH 成功的频率。
- `refresh_interval` 的字段级 PATCH 不得被其它不涉及刷新频率的旧状态 / full-save 意外覆盖。仪表盘、大屏、拓扑图布局保存走 `PUT` 且 payload 不含该字段；模型字段一旦带 `default=0`，DRF 非 partial `PUT` 可能把省略字段写成默认值。本期用最小修复（序列化在 update 时省略该字段的 default，和/或 PATCH 成功后同步 canonical client state），不为这一字段改整套保存架构。网络拓扑布局保存走 `PUT .../config/` 只换 `view_sets`，不碰该字段；目录侧栏元数据编辑走 `PATCH` 且不含该字段。
- 无编辑权限、分享会话、内置画布：用 saved 值作为 effective 初值开定时器；改下拉只改本次会话，不请求写回。内置画布初始化会删掉重建，因此内置对象上的频率也不写回。
- 分享详情对四种画布都返回 `refresh_interval`。分享页露出与工作台相同的刷新控件，并按 **effective**（初值=saved）自动刷。网络拓扑分享态现在把这组控件藏掉了，本期要露出来。
- YAML 导入导出带上 `refresh_interval`。缺字段或非法值（含旧秒语义 `60`）当 `0`，不让整包失败。可选字段，不为此单独升 YAML schema 主版本。架构图 YAML 不增加该字段。报表 YAML 的 `refresh_interval` 见 [`ops-analysis-report-canvas-toolbar`](../ops-analysis-report-canvas-toolbar/spec.md)。仓库当前导出从未写出该字段；DB 存量 `60` 用 data migration 写成 `0`，不要在运行期长期 `60 => 0` 猜版本。仓库没有独立的画布复制 API，「复制」即同一套 YAML/导入字段契约。
- 周期刷新只重拉运行态数据：仪表盘/大屏组件查询、拓扑图单值与图表节点、网络拓扑指标与连线状态。不重新加载画布布局、组件配置、节点位置，不重置筛选和命名空间草稿。编辑态同样继续刷数，但不得覆盖正在编辑的配置表单或侧栏草稿。
- 刷新原因要在取数路径上显式区分，不能再用「同一次 reload」同时表达手动和周期：

| 原因 | Loading | 失败 |
|---|---|---|
| 首次进入（还没有成功数据） | 出 | 现有错误态 |
| 手动刷新 | 出 | 现有错误态 |
| 统一筛选 / 命名空间变更 | 出 | 现有错误态 |
| 周期刷新 | 不出；已有成功数据则保留 | 已有成功数据则保留；从未成功则保持现有错误态；不弹会刷屏的 toast |

- 周期刷新的「不出 loading」覆盖所有运行态表面：组件级 Spin、表格 loading 蒙层、拓扑单值 `○ ○ ○` 动画、拓扑图表节点整块 Spin、网络拓扑指标清空后的小圈、场景组件蒙层。有旧值就留着，新值到了再换。
- 画布配置了周期刷新但首次加载失败、当前从未取得成功数据：首次失败仍显示现有错误态；定时器按 effective interval 继续静默重试；重试失败保持错误态，不反复 toast、不清空成 loading；某次重试成功后恢复数据展示。不因首次失败自动把频率打成关。
- 仪表盘/大屏组件取数已有「是否首次」判断和 `fetchIdRef` latest-wins；本期要补「本次是否周期刷新」，避免首次判断过了仍把 `loading=true` 传进子组件并换成 Spin。周期失败不得走现有 `setRawData(null)` 清数据路径。最高接缝是现有组件请求决策，而不是为每种图表各写一套静默逻辑。
- 相对时间（近 15 分钟、1 小时等）每次周期刷新按此刻重算查询窗口；用户确认过的自定义绝对区间保持起止不变。拓扑图、网络拓扑没有这套时间窗，不受影响。
- 定时器只绑定 `effectiveRefreshInterval`。`TimeSelector` 本身没有计时契约，只回调频率毫秒值；四种画布必须共用下面这条节奏，不能各自解释。现有拓扑图 `setInterval` 已是「切档后从此刻重新计时、不立即多打一轮」，本期沿用：
  - `off -> 1m/5m/10m`：从切换时刻开始计时，不立即额外请求
  - 非零档互切（如 `1m -> 5m`）：从切换时刻重新计时
  - 任意档 -> `off`：立即停止后续 tick，不取消已经在途的请求
  - 手动点击刷新：执行一次手动刷新，**不重置**周期计时
  - 打开画布时的首次取数走现有加载；effective > 0 时等满一个间隔再进入周期 tick，不要在首次成功后立刻再打一轮
- 仅当 `effectiveRefreshInterval > 0` 时处理页签可见性：
  - hidden：暂停周期 tick，不累计 missed ticks
  - visible：立即静默刷新一次，然后从恢复可见的时刻重新开始完整 interval
  - effective 为 `off` 时，hidden → visible **不得**因 visibility change 单独触发刷新
  全屏呈现不是 `document.hidden`，继续按 effective interval 正常刷新；筛选保持进入全屏时的状态。
- single-flight 跟随真实 request owner，禁止画布级 `isRefreshing` 大锁（一个慢组件不得阻塞其它组件的周期刷新）：
  - 仪表盘 / 大屏：每个 Widget 自己的取数（现有 `fetchIdRef` + 按 widget 的 inflight cache key）
  - 拓扑图：每个单值节点 / 图表节点各自的取数（现无 generation，本期补上）
  - 网络拓扑：现有运行态 batch（`loadConfiguredRuntime`）；batch 内节点/连线并发保持现状，不要升成整图画布锁去挡其它请求
- interval vs interval：同一 owner 上一轮周期请求仍在途时，下一轮 interval tick **skip**。被 skip 后不在请求结束时补发，等下一个正常 tick。
- 用户主动请求 vs interval：手动刷新、筛选变化、命名空间变化、运行参数变化等用户主动请求 **不得**因为 interval 仍在途而被 skip 或并入 interval 的 inflight promise。用户请求发出后成为最新 generation。
- stale response 是跨刷新原因的 latest-wins / generation 合同，每个实际数据请求 owner 维护 generation：
  - 新的有效请求使旧 generation 失效
  - 写入 data / error / loading 前检查自己是否仍是当前 generation
  - stale 的成功响应不得覆盖当前 data；stale 的 error 也不得把当前成功状态切成 error
  - 组件 unmount / 画布切换后返回的旧响应不得写回
  仪表盘/大屏复用现有 `fetchIdRef`（不要另造一套）；拓扑图节点取数目前无 generation，必须补到同一合同；网络拓扑复用现有 `runtimeLoadGenerationRef`，但手动刷新不得再复用「同 canvasId 则返回在途 promise」的合并逻辑。
- 报告订阅、PDF 渲染、分享会话的服务端快照不引入前端定时器，也不在渲染页做周期刷新。

## Testing Decisions

好的测试只断言用户能观察到的行为：某次刷新出不出 loading、旧值在失败后是否还在、保存后再读是否仍是该档、隐藏页签是否不再发周期请求。不断言定时器实现细节或具体组件树。

优先打最高接缝：

- 组件请求/loading 决策：已有成功数据时，周期刷新不进入 loading；手动刷新、筛选/命名空间变更进入 loading；周期失败保留上一轮数据。先验是现有组件取数失败测试，把原因差补进同一决策函数。
- 画布 `refresh_interval`：默认 0；合法四档可读写；非法值拒绝；网络拓扑存量经 migration 后为 0。先验是画布详情/更新与分享序列化测试。
- session override 实际驱动 effective interval 定时器，且不写服务端。
- 频率 PATCH 失败后 UI 与 timer 都回退到 saved value。
- 频率 PATCH 成功后再 `PUT` 保存布局/其它画布配置，不得把频率写回旧值。
- 分享载荷：四种画布都带 `refresh_interval`；无编辑权限时改频率不写回。
- YAML：导出带该字段；缺字段或非法值（含 `60`）导入为关。先验是导入导出 schema 与 export/import 服务测试。
- 拓扑图：周期刷新不把单值节点打成 loading 动画、不把图表节点整块换成 loading；手动刷新仍出 loading。
- 网络拓扑：周期刷新不把指标值清空成 loading；手动刷新可以。
- 相对时间窗按此刻重算、绝对区间不变，覆盖仪表盘/大屏统一筛选。
- `off` 时 hidden → visible 不触发刷新；effective > 0 时 hidden 暂停、visible 静默补一次并从此刻重新计时。
- 切档后从切换时刻重新计时；`off -> 非零` 不立即额外请求；手动刷新不重置 interval cadence。
- 一个慢 Widget / 节点不阻塞其它 owner 的周期刷新。
- interval 在途时用户主动请求仍发出；用户新请求成功后，旧 interval 的 data/error 不得覆盖。
- 首次失败后周期仍按间隔静默重试，成功后恢复数据展示。
- 组件 unmount / 切换画布后的旧响应不得写回。

不把四种画布的完整页面挂载作为默认测试面；只在接缝无法表达的交互（工具栏写回、分享态控件可见）才补轻量组件测试。

## Out of Scope

- 架构图的周期刷新。报表周期刷新见 [`ops-analysis-report-canvas-toolbar`](../ops-analysis-report-canvas-toolbar/spec.md)。
- 把频率做成组件级设置，或开放任意秒数。
- 内置画布上持久化用户改过的频率。
- 秒级推送、WebSocket、后端推数。
- 报告订阅 / PDF 渲染链路的自动刷新。
- 周期失败的画布级错误条或会刷屏的 toast（允许刷新按钮上不挡内容的失败标记，但不是本期必须项）。
- 修改统一筛选语义、权限模型或画布目录结构。

## Further Notes

- 术语：对象是分析画布；`refresh_interval` 是画布级运行设置。不要写成「定时任务」或报告订阅的「执行周期」。
- 现有拓扑图频率只活在当前会话，网络拓扑后端 60 秒从未接到 UI。本期以后，工作台与分享页都读画布字段；未保存过的盘一律为关。
- 交付后若要更新运营分析功能清单，以本 spec 的用户故事为准，不在本期同步改 capability 正文。

## Completion Evidence

- 四种运行态画布（仪表盘、大屏、拓扑图、网络拓扑）接入统一刷新控件与画布级 `refresh_interval`（0 / 60000 / 300000 / 600000）。有 `view-EditChart` 且非内置时 field PATCH 当场写回；分享/无权限/内置只改本次 session。周期刷新静默换数，手动/筛选/命名空间仍出 loading。
- 后端：模型字段、migration（网络拓扑存量一律写成 0）、PUT 省略字段不覆盖、YAML 导入导出、分享 payload。
- 请求 owner 用 `generation` + `inflightCount`：同一 owner 只要有物理请求在途，新的 periodic/visibility 就 skip；主动请求仍 latest-wins。session override 在同画布 saved 回灌时保留，切画布重置；PATCH 成功写入 saved baseline。
- 聚焦测试通过（2026-08-14）：
  - `cd server && .venv/bin/pytest apps/operation_analysis/tests/test_canvas_refresh_interval.py apps/operation_analysis/tests/test_import_service.py -q`（51 passed）
  - `cd web && pnpm exec vitest run src/app/ops-analysis/utils/__tests__/canvasRefreshInterval.test.ts src/app/ops-analysis/utils/__tests__/canvasRefreshTimer.test.ts src/app/ops-analysis/hooks/__tests__/useCanvasPeriodicRefresh.test.ts src/app/ops-analysis/components/__tests__/widgetDataRenderer.fetchError.test.tsx src/app/ops-analysis/(pages)/view/topology/hooks/__tests__/topologyOwnerRequest.test.ts src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/networkStatusTopology.fetch.test.tsx`（67 passed）
- 本次涉及的前端生产文件 ESLint：0 error。

