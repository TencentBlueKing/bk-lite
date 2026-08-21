# 实施方案：AI 悬浮机器人页面上下文

对应 spec：`./spec.md`。M1 与 M2 可并行；M3 依赖 window bridge；M4 依赖 chart-capture + pilots manifest。

## M1 后端注入链路（server/apps/opspilot）

1. `views.py::execute_skill_channel_chat`：读取可选 `page_context`，透传服务层。不改嵌入式/IM。
2. `services/skill_channel_chat_service.py`：
   - `persistable_user_message_text`：多模态 list 抽纯文本再 `append_message`。
   - `inject_page_context(..., mode="inline")`：`<current_page>` 模板 + 截图转 `image_url`；未知 mode 跳过并打日志。
   - 文本预算 8K（先保高 priority，装不下的低 priority 整段丢弃）；图片最多 6 张、单图 base64 >500KB 丢弃。
   - `stream_skill_channel_chat`：先落库原文 → `build_skill_chat_params` → 再 inject 到 `params["user_message"]`。
3. 测试：`tests/test_skill_channel_page_context.py`。

## M2 采集框架（web/src/components/ai-page-context/）

- `registry.ts`：hook 注册 + `collect()`（2s 超时、合并、裁剪）。`window.__BK_AI_PAGE_CONTEXT__`。`hasAvailable()` 供 chip 显示。
- `pilots.ts`：路由旁路 manifest，仅 `collect()` 时动态 import。
- `chart-capture.ts`：`echarts/core` `getInstanceByDom` → 600px JPEG + `getOption()` caption。
- `useAiPageContext.ts`：保留给深度集成。

## M3 webchat 桥接

- `@webchat/core` 增加 `collectContext` / `hasPageContext`。
- `Chat.tsx`：chip「已附加当前页面」；发送时把快照放入独立字段 `page_context`。
- `GlobalWebchat` 注入回调；`webchat.js?v=` 升版本。构建：`webchat` 目录 `npm run build`。

## M4 monitor 仪表盘试点（零侵入）

- 新增 `web/src/app/monitor/(pages)/view/dashboard/dashboard.pilot.ts`。
- 不修改 `simple-dashboard-core.tsx` / `useECharts.ts` / 各对象 dashboard。

## 回滚

- 后端字段可选。
- 前端：`GlobalWebchat` 不注入 `collectContext` 即关闭。
