# Control Console iframe 屏显模式

门户或第三方系统可以把 Control Console（WeOpsX）嵌进 iframe。通过 URL 查询参数进入屏显模式后，平台壳层导航隐藏，只保留当前业务页。

**本阶段范围：壳层基础 + 运营分析牵头。** 不是全站通用 iframe 嵌入已完工。

## 普通 URL vs `screen=true`

- 普通地址（例如 `https://weopsx.example.com/ops-analysis/view`）：完整产品，含顶栏与菜单。
- 带屏显参数（例如 `https://weopsx.example.com/ops-analysis/view?type=dashboard&id=<id>&screen=true`）：无平台导航，适合 iframe。运营分析请带上画布 `type` / `id` 深链。
- 参数名固定为 `screen`。值为大小写不敏感的 `true` 或 `1` 时开启；缺省或其他值均为普通模式。
- 浏览器直接打开带参 URL 与放进 iframe 的效果一致。

示例：

```html
<iframe
  src="https://weopsx.example.com/ops-analysis/view?type=dashboard&id=<id>&screen=true"
  title="WeOpsX"
  style="width: 100%; height: 100%; border: 0;"
></iframe>
```

## 藏什么 / 不藏什么

屏显模式隐藏：平台顶栏、一级导航、应用业务二级侧栏、全局 AI 助手入口。运营分析屏显范围含 `/ops-analysis/view` 左侧目录/侧栏与折叠钮，以及 `/ops-analysis/settings` 管理分段菜单（数据源 / 连接库 / 命名空间）；深链仍打开对应画布。其它 app 业务自挂的二级菜单仍可能出现（已知限制）。

保留：当前路由的业务内容与页内工具条（筛选、编辑、画布控件等），以及合规水印。不做默认只读。

未带参数时，现有导航与菜单不受影响。

## 刷新与登录回跳

刷新和深链只要 URL 仍带 `screen=true`，就会保持屏显。

站内官方导航（顶栏、侧栏等）会在屏显会话中继续带上该参数。运营分析 view 内切换画布 / 最近打开会保留 `screen`。从登录页带 `screen=true` 进入（冷开 `/auth/signin?screen=true`），或从业务页屏显再去登录后回跳，落地后仍保持屏显。登录回跳若丢掉查询参数，同标签页会写回 `screen=true`，不会把它做成长期偏好：之后用不带参数的地址打开，仍是完整壳层。

屏显下部分业务页可能未铺满视口，或出现底部裁切 / 露底。**高度对齐延期**，本阶段不保证。

## 本阶段透传边界（二期）

本阶段只保证 **运营分析屏显会话内** 点选、刷新后壳层不回流。从运营分析跳到监控、CMDB、日志等其它模块，或其它模块内部的 `router.push`，可能丢掉 `screen` 并恢复平台壳层。屏显高度对齐（铺满 / 露底 / 裁切）同样延期。按反馈二期补，不作为本阶段验收失败。

## 同站前提与建议宽度

本能力只保证壳层隐藏与参数行为。默认按同站（或现网已经能在 iframe 里维持登录）部署使用。跨站嵌套时浏览器可能限制第三方 Cookie，登录态需运维单独保证，不在本能力范围内。

屏显模式会取消平台级 1280px 最小宽度，避免外壳先撑出横向滚动。业务页若自己有最小宽度，窄 iframe 里仍可能页内横滚。建议宿主给业务页足够宽度（桌面控制台常见为 ≥1280px）。
