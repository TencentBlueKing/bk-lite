# 实施方案：AI 悬浮机器人页面上下文

对应 spec：`./spec.md`。M1 与 M2 可并行；M3 依赖 window bridge；M4 依赖 chart-snapshot + pilots codegen。

## M1 后端注入链路（server/apps/opspilot）

1. `views.py::execute_skill_channel_chat`：读取可选 `page_context`，透传服务层。不改嵌入式/IM。
2. `services/skill_channel_chat_service.py`：
   - `persistable_user_message_text`：多模态 list 抽纯文本再 `append_message`。
   - `inject_page_context(..., mode="inline")`：`<current_page>` 模板 + 截图转 `image_url`；未知 mode 跳过并打日志。
   - 文本预算 8K（先保高 priority，装不下的低 priority 整段丢弃）；图片最多 6 张、单图 base64 >500KB 丢弃。
   - `_focus_page_context`：点名图表只留匹配截图。
   - `_history_for_focused_charts`：**本轮点名任一图表 → 清空历史**（防换时间筛选复述旧时间窗）。
   - `stream_skill_channel_chat`：先落库原文 → `build_skill_chat_params` → 再 inject 到 `params["user_message"]`。
3. 测试：`tests/test_skill_channel_page_context.py`。

## M2 采集框架（web/src/components/ai-page-context/）

- `registry.ts`：hook 注册 + `collect()`（2s 超时、合并、裁剪）+ `getMessage`/`getContext` 缓存。`window.__BK_AI_PAGE_CONTEXT__`。
- `pilots.ts` + `pilots.generated.ts`：codegen 扫 `*.pilot.ts`，`collect()` 时动态 import。
- `chart-snapshot/`：`echarts/core` `getInstanceByDom` → 600px JPEG + `captionFromOption`（含趋势图 `横轴`）。
- `useAiPageContext.ts`：保留给深度集成。

## M3 webchat 桥接

- `@webchat/core` 增加 `collectContext`。
- `Chat.tsx`：发送前采集，快照放入独立字段 `page_context`；**无「已附加当前页面」chip，每轮默认附加**（有 collect 且有匹配源时）。
- `GlobalWebchat` 注入回调；`webchat.js?v=` 升版本。构建：`webchat` 目录 `npm run build`。

## M4 monitor 仪表盘试点（零侵入）

- 新增 `web/src/app/monitor/(pages)/view/dashboard/dashboard.pilot.ts`。
- **不修改** `simple-dashboard-core.tsx` / 各对象 dashboard：时间筛选经 DOM 指纹写入 `currentTime`；图表经 echarts 截图 + 横轴 caption。

## 回滚

- 后端字段可选。
- 前端：`GlobalWebchat` 不注入 `collectContext` 即关闭。

## v2 里程碑（对应 spec「修订 v2」，已落地）

V1 截图公共化：`chart-capture` 迁至 `web/src/components/chart-snapshot/`。

V2 新契约与缓存：`getMessage` / `getContext(toolkit)`；registry 内存缓存；删除前端问法筛图。

V3 codegen：`generate-ai-pilots.mjs` → `pilots.generated.ts`，挂 prepare-enterprise。

V4 monitor 试点迁移：全量截图 + 上限。

V5 后端多模态与超限：`LLMModel.is_multimodal`；裁图；单轮/会话超限错误流。

V6 文档与测试：`app-integration.md` 按新契约重写；相关单测。

## v3 落地补丁（对应 spec「修订 v3」）

- 去掉 chip，默认每轮附加页面上下文。
- monitor pilot：DOM 读时间筛选 + KPI/状态指纹 → `currentTime`；sections 写明筛选；Console 诊断日志。
- `captionFromOption` 增加 `横轴`；点名图表一律丢历史；引导语禁止沿用旧时间窗。
- 对接文档 [`app-integration.md`](./app-integration.md) 与 spec 同步。
