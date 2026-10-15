# 运营分析大屏自定义背景图

Status: implemented

Completion evidence:

- 背景解析：`screenBackground.test.ts` 断言 image 为 cover 居中，纯色路径不变，超限与非法格式在写入前拒绝。
- 规范化：`viewport.normalize.test.ts` 保留合法 image、缺 `src` 与非法 src 回落主题预设，改分辨率时克隆不丢 `src`。
- 编辑器：`screenEditorPanels.test.tsx` 上传写入 image、清除、切纯色或切回壁纸不再带 `src`、换主题保留图片、超限与非法格式不写入。
- 导入导出：`test_export_and_viewsets.py` 的 `test_normalize_screen_keeps_custom_image_background_through_yaml_rewrite` 断言存储、导出、再导入仍是同一 `type` 与 `src`。

## Problem Statement

大屏搭建者已经能在画布设置里选纯色或少量内置壁纸，但投屏场景常需要客户品牌图、机房实景或活动主题图。现在不能上传自己的图片，只能凑合用预设，一屏的视觉辨识度不够。

## Solution

在现有大屏画布背景能力上增加第三种模式：上传自定义图片。图片随大屏草稿写入 `viewport.background`，编辑、查看、全屏、分享和 PDF 走同一套背景解析，铺满设计画布。不做对象存储、不做填充方式控件；用前端体积与格式限制把 `view_sets` 膨胀压住。

## User Stories

1. 作为大屏搭建者，我希望在画布设置的背景区选择「自定义图片」并上传一张图，从而立刻在设计画布上看到自己的壁纸。
2. 作为大屏搭建者，我希望上传后可以清除自定义图或切回纯色 / 预设壁纸，从而不必为换背景新建一屏。
3. 作为大屏搭建者，我希望保存后查看、全屏、分享和 PDF 仍显示同一张图，从而投屏与编辑所见一致。
4. 作为大屏搭建者，我希望选了不支持的格式或过大的文件时得到明确提示且不写入草稿，从而不会悄悄弄坏保存或导入导出。
5. 作为已有大屏的维护者，我希望打开仍只有纯色或预设背景的大屏时行为不变，从而现网大屏不会被这次改动打坏。

## Implementation Decisions

### 范围与产品边界

- 只改运营分析**大屏**的画布背景。仪表盘、报表、拓扑、架构图、网络拓扑不跟。
- 在上一期「纯色 / 预设壁纸」之上增加「自定义图片」；不替换现有两种模式。
- 不做独立文件服务或 MinIO 壁纸资源表；图片以 data URL 形式进入 `viewport.background`，随画布 `view_sets` 草稿保存、导入导出与分享载荷一起走（对齐拓扑节点自定义 `logoUrl` 的既有做法）。
- 不做平铺、对齐、九宫格、模糊遮罩、多图轮播或视频背景。
- 填充方式固定为铺满设计画布（`cover` + 居中），不提供填充控件。
- 不因此单独升 YAML 主版本。

### 背景模型

`viewport.background` 在现有联合类型上增加 image 分支：

```ts
type ScreenBackgroundConfig =
  | { type: 'color'; color: string }
  | { type: 'preset'; key: string }
  | { type: 'image'; src: string };
```

- `src` 为本期的 data URL（`data:image/...;base64,...`）。规范化与克隆必须原样保留合法 image 背景，不得回落成主题默认预设。
- 非法或缺 `src` 的 image 在规范化时回落为主题默认预设（与缺背景一致），避免脏数据卡死渲染。
- 切换到纯色或预设时，新背景对象不再携带旧 `src`。

### 上传约束

- 允许格式：`image/png`、`image/jpeg`、`image/webp`。
- 文件大小上限：2MB（按原始文件字节数在前端拦截；超限或格式不对只提示，不写入草稿）。
- 读取方式：本地 `FileReader` 转 data URL，再写入当前编辑草稿的 `viewport.background`；与样式改动一样即时反映到画布，整屏仍靠顶栏保存落库。
- 取消编辑仍回退到上次成功保存（含旧背景）；不另做上传事务。

### 渲染与呈现路径

- 背景解析统一产出画布层 CSS：image 使用 `background-image: url(src)`，`background-size: cover`，`background-position: center`，`background-repeat: no-repeat`。
- 编辑画布、查看、全屏、分享、PDF / 订阅渲染共用同一解析结果，不在某一呈现路径单独写死背景。
- 主题（`screen-dark` / `screen-light`）与自定义图独立：换主题不自动清掉已上传的图；切到预设壁纸时仍按主题过滤可选预设列表（现行为不变）。

### 编辑器

- 未选中元素时，右侧画布设置的背景区由两档扩展为三档：科技壁纸（预设）/ 纯色背景 / 自定义图片。
- 自定义图片档展示：上传入口、当前图缩略预览、清除。上传成功即切换为 image 背景；清除后回落主题默认预设。
- 不在此期增加填充方式、透明度或遮罩控件。

### 持久化与导入导出

- 后端大屏 `view_sets` 校验与规范化放行 `background.type === 'image'` 及 `src`。
- YAML 导入导出带上 image 背景；缺背景或旧结构行为不变。
- 不做服务端二次压缩或内容扫描；体积风险靠前端 2MB 上限约束。若后续 `view_sets` 体积成为事故，再单独立项迁对象存储。

## Testing Decisions

测对外行为，不测 CSS 像素和 base64 内容本身。优先复用大屏现有接缝：背景解析、`view_sets` 规范化、画布设置面板、导入导出。

1. **背景解析**：`type: 'image'` 且 `src` 合法时产出 cover 居中样式；纯色与预设路径不被回归。
2. **规范化**：已存 image 背景不被重置；缺 `src` 或非法 image 回落主题默认；克隆 viewport 不丢 `src`。
3. **编辑器**：切换到自定义图片并给出 data URL 后，草稿 `viewport.background` 为 image；清除或切回纯色 / 预设后不再携带旧 `src`；超限或非法格式不写入。
4. **导入导出**：导出含 image 背景；再导入后仍为同一 `type` 与 `src`；仅有纯色 / 预设的旧 YAML 行为不变。

Prior art：`viewport.normalize.test.ts`、背景相关的 `screenEditorPanels` 测试、`test_export_and_viewsets.py` 中 adapter/背景保留用例；拓扑自定义 logo 的本地读图交互可作上传 UX 参考，不必复用其测试文件。

## Out of Scope

- 对象存储 / MinIO 壁纸资源、独立上传 API、签名 URL
- 填充方式（contain / 平铺 / 拉伸）、对齐、九宫格、模糊与遮罩
- 视频背景、多图轮播、GIF 动效保证
- 服务端压缩、病毒扫描、跨画布图片库
- 仪表盘或其他画布类型的自定义背景
- 修改主题色板或内置预设壁纸清单（可另项加减预设）

## Further Notes

- 上一期 `ops-analysis-screen-basic-layout` 将「壁纸上传」列在 Out of Scope；本变更是在该底座上的增量，不重做三区编辑器或适配算法。
- 选用 data URL 是有意的短路径：与拓扑节点自定义图一致，分享与导入导出无需额外鉴权。代价是 `view_sets` 变大，故 2MB 上限是产品约束而非实现细节。
- 若实现中发现分享页或 PDF 对超长 data URL 有既有限制，应在实现时用同一上限挡住编辑端，并在测试中锁定「超限不写入」，而不是放宽存储。
