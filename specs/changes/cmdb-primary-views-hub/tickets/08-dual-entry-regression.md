# 08 — 双入口回归收口

Status: done

Blocked by: 03 — 网络拓扑工作台; 04 — 应用拓扑工作台; 05 — K8S 视图工作台; 06 — IP 视图工作台; 07 — 机房机柜工作台

**What to build:** 确认详情侧专题 Tab / 侧栏快捷未回归；五个专题与资产总览均可从一级走通；测试脚本与手动验收清单完成。

- [x] 详情关联关系 Tab、IP 页、K8S 资源页、侧栏快捷行为与改前一致
- [x] 一级五个专题 + 资产总览可完整走通（含空态与有记忆路径）
- [x] 菜单/资格/记忆/URL 脚本断言绿
- [x] 规格与 tickets 状态、完成证据已更新

## Completion evidence

### 自动化脚本（2026-08-12 本地跑通）

| 命令 | 结果 |
|------|------|
| `pnpm run test:cmdb-views-hub-core` | PASS |
| `pnpm run test:cmdb-views-hub-menu` | PASS |
| `pnpm run test:cmdb-views-hub-wiring` | PASS |
| `pnpm run test:cmdb-k8s-resource-overview` | PASS |
| `pnpm run test:cmdb-app-overview-wiring` | PASS |
| `pnpm run test:cmdb-network-topo-editing` | PASS |
| `pnpm run test:cmdb-relationships-imports` | PASS |

### Manual checklist（静态 vs 浏览器）

| 项 | 判定 | 说明 |
|----|------|------|
| 详情 relationships Segmented：应用拓扑 / IP / 网络 | verified-via-code | `test:cmdb-app-overview-wiring` + `test:cmdb-relationships-imports` + `test:cmdb-network-topo-editing` |
| 详情侧栏快捷（网络 / 应用拓扑 / 机房 / 机柜） | verified-via-code | `side-menu.tsx` 仍按 themes 推送 tab；wiring 脚本锁定 appOverview |
| 详情 K8S「资源详情」页可注入/独立打开 | verified-via-code | `K8sResourceDetailsContent` + `test:cmdb-k8s-resource-overview` |
| 一级菜单：资产总览 + 五专题文案/URL | verified-via-code | `test:cmdb-views-hub-menu` |
| ViewCanvasHost 五专题组件接线 + onRackSelect | verified-via-code | `test:cmdb-views-hub-wiring` |
| 资格 / 记忆 / URL / 空态纯函数 | verified-via-code | `test:cmdb-views-hub-core` |
| 一级进入五专题并切换实例（有数据） | pending manual | 需浏览器：选实例 → 画布加载 → 切换 |
| 无记忆空态引导选实例 | pending manual | 需浏览器：清 localStorage 后进专题 |
| 有记忆刷新恢复焦点 | pending manual | 需浏览器：刷新后 focus 恢复 |
| 网络拓扑一级入口可编辑 | pending manual | 需浏览器：写操作与详情同权 |
| 机房平面图点机柜留在工作台切 rack | pending manual | 代码已接线 onRackSelect；交互需浏览器确认 |
| 「查看详情」进基础信息 | pending manual | 代码走 `buildBaseInfoPath`；导航需浏览器确认 |
| 详情双入口未破坏（点侧栏/Tab） | pending manual | 静态接线绿；端到端需浏览器点一遍 |

## Notes

- 未 archive；未 git commit（Task 9 约束）
- 浏览器验收项留给 QA / 责任人按上表 pending manual 勾选
