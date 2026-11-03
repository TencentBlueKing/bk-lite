# 运营分析大屏：全屏铺满改为视口像素布局重算

Status: implemented

Supersedes (presentation only): `specs/changes/ops-analysis-screen-basic-layout/spec.md` 中「`fill` 用非等比 `scaleX/scaleY` 整层拉伸」的呈现约定。存盘模型、三种显示方式枚举、编辑 / PDF 强制 contain 不变。

## 行为

仅当 `resolveScreenDisplayAdapter` 解析为 `fill`，且是全屏或分享、且非 `forceContain`：

- 画布等于视口，外层 `transform` 为 `none`，不加 `screen-tech-canvas--stretched`。
- 组件呈现几何：`left = round(x * sx)`，`top = round(y * sy)`，`width = max(1, round(w * sx))`，`height = max(1, round(h * sy))`。不写回设计坐标。
- 图表字号密度是 `screenDensity`（相对 1440×810，夹在 0.72–1.16）。`widgetUiScale = screenDensity`，图表视口倍数为 1。这等于旧 transform 路径的屏幕字号 `designPx × screenUiScale × fitScale`，只写一次。交互菜单的画布倍数视为 1，禁止再乘一层 `fitScale`。
- 标题、时钟和其它 chrome 文字乘 `fitScale`，不乘 `screenDensity`。编辑态这些字是设计 px，再由外层 transform 乘 `fitScale`；视口像素没有这层 transform，直接乘 `fitScale` 才和编辑态里相对画布的比例一致。4K 盘名 56px 若乘 `screenDensity`（约 1.16）会比编辑态大约一倍。
- 形状描边、阴影、圆角，以及 Vision 面板边框，按设计厚度 × `fitScale`。Vision 先用 `client ÷ sx/sy` 回到设计尺寸选档，再乘 `fitScale`；不要对已经映射的 client 尺寸再升一档。`object-fill` 装饰图仍可能变形。
- 编辑、非全屏查看、PDF（`forceContain`）、`fitWidth`、`fitHeight` 仍走设计尺寸盒子加等比 `transform`。

## 已知限制

- 布局仍按 `sx` / `sy` 拉开，非 16:9 窗口上构图会变。
- 装饰图和壁纸随盒子非等比变宽变高时，位图仍可能变形。
- 非正方形盒内的 CSS 圆可以变成椭圆；本期不做反向补偿。

## Completion evidence

- 闸门：`viewport.normalize.test.ts` 的 `shouldUseViewportPixelLayout`。
- 轴比例与字号取 screenDensity、4K 不再收成 fitScale：`metrics.adapter.test.ts` 的 `viewport pixel font scale`。
- 图表轴、中心数字、图例倍率等于 widgetUiScale：`chartViewportFont.test.tsx`。
- 标题和时钟乘 fitScale、编辑态仍是设计 px：`metrics.adapter.test.ts` 的 `viewport pixel chrome title and clock`。
- 形状描边 × fitScale、Vision 不按已映射 client 升档：`screenShape.test.ts`、`screenChromeSkins.test.tsx`。
- 菜单画布倍数：`interactionMenuScale.test.ts` 的 viewport pixel 用例。
- 画布无 `scale(sx, sy)`、几何抽样、编辑 / 查看 / PDF / fitWidth / fitHeight 仍走旧路径：`screenCanvas.rerender.test.tsx`。
- 机柜字号不再取 `1/fitScale`：`room3D/__tests__/readableScale.test.ts`。
- 标题/时钟密度：`screenChromeRenderer.clock.test.tsx`。
