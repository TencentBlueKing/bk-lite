# Control Console iframe 屏显模式

门户或第三方系统可以把 Control Console（WeOpsX）嵌进 iframe。通过 URL 查询参数进入屏显模式后，平台壳层导航隐藏，只保留当前业务页。

**本阶段范围：壳层基础 + 运营分析牵头 + 路由级业务侧栏/分段隐藏 + 合同内 `screen` 透传 + 屏显高度链收口。** 不是全站客户端跳转零例外，也不是通用 iframe 嵌入已完工。对象树隐藏、跨站 framing 仍按反馈另立。

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

屏显模式隐藏：平台顶栏、一级导航、应用业务二级侧栏、全局 AI 助手入口，以及业务页自挂的路由级侧栏/分段菜单（含运营分析 settings 的数据源 / 连接库 / 命名空间、监控/日志集成详情、CMDB 资产/模型详情、OpsPilot 详情、补丁库、通道、应用管理、节点管理云区域等）。有页头的详情页仍保留页头。运营分析 `/ops-analysis/view` 另隐藏左侧目录/侧栏与折叠钮；深链仍打开对应画布。

不隐藏：监控/日志等工作区对象树、页内 Tab 或 Segmented（例如监控视图 list/hive、CMDB 特征库 Tabs）。iframe 请深链到具体子路由（例如补丁库 `/patch-manager/library/windows`，而不是只有父路径）。

保留：当前路由的业务内容与页内工具条（筛选、编辑、画布控件等），以及合规水印。不做默认只读。

未带参数时，现有导航与菜单不受影响。

## 刷新与登录回跳

刷新和深链只要 URL 仍带 `screen=true`，就会保持屏显。

站内官方导航（顶栏、侧栏等）会在屏显会话中继续带上该参数。运营分析 view 内切换画布 / 最近打开会保留 `screen`。从登录页带 `screen=true` 进入（冷开 `/auth/signin?screen=true`），或从业务页屏显再去登录后回跳，落地后仍保持屏显。登录回跳若丢掉查询参数，同标签页会写回 `screen=true`，不会把它做成长期偏好：之后用不带参数的地址打开，仍是完整壳层。

屏显下业务区有确定视口高度：外层锁 `h-screen`，主区满高，`data-console-screen-workspace` 作为默认滚动口，大屏 / 拓扑 / 架构应能铺满或显示画布。不要把分享页的整页 `overflow-hidden` 套到所有屏显路由。列表页在工作区内滚动。

iframe 内的 `h-screen` 等于 **iframe 自己的视口**。宿主把 iframe 裁矮时，锁的是这块矮视口，不会按宿主窗口再撑高。业务页若仍用 `calc(100vh - 顶栏)` 估算高度，窄高差额属于已知残留。

## 透传

刷新和深链只要 URL 仍带 `screen=true`，就会保持屏显。站内官方导航、登录回跳、运营分析 view 内切画布会继续带上该参数。

本阶段另外保证：从运营分析表格「当前页打开」或拓扑节点跳到同站监控 / CMDB 等业务页，以及监控、日志、CMDB、系统管理、节点管理、OpsPilot、补丁管理里合同内的主路径跳转，仍带 `screen`，壳层不回流。屏显下这些同站动作走当前 iframe，不会为了打开详情再弹出新标签。明确配置为「新窗口」的产品动作、外链和下载不强制改同框，也不强制带 `screen`。

URL 仍是唯一对外契约。无参冷开仍是完整壳层。登录回跳可用同标签短备份恢复参数；业务页自己丢掉 `screen` 时不会自动写回。

仍可能丢掉 `screen` 的已知缺口：告警、作业、APM、MLOps 的内部跳转（APM 大量 `Link` 尤甚），以及服务端 `redirect()`。

## 同站前提与建议宽度

本能力只保证壳层隐藏与参数行为。默认按同站（或现网已经能在 iframe 里维持登录）部署使用。跨站嵌套时浏览器可能限制第三方 Cookie，登录态需运维单独保证，不在本能力范围内。

屏显模式会取消平台级 1280px 最小宽度，避免外壳先撑出横向滚动。业务页若自己有最小宽度，窄 iframe 里仍可能页内横滚。建议宿主给业务页足够宽度（桌面控制台常见为 ≥1280px）。
