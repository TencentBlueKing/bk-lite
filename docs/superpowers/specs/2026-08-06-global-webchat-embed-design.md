# BK-Lite Web 全局 WebChat 嵌入设计

## 目标

在 `bklite_web` 的标准控制台页面中嵌入现有 `webchat/` 浏览器组件。用户登录后，只要拥有 OpsPilot 应用访问权限，即可通过右下角悬浮按钮访问指定 Chatflow。

本次只完成嵌入和联通，不修改 WebChat 的请求字段契约、OpsPilot 后端接口或会话模型。

## 固定接口

浏览器通过现有 Next.js 同源代理访问：

```text
/api/proxy/opspilot/bot_mgmt/execute_chat_flow/80/embedded_chat-1786007476479/
```

该地址对应用户提供的生产接口：

```text
https://bklite.canway.net/api/v1/opspilot/bot_mgmt/execute_chat_flow/80/embedded_chat-1786007476479/
```

前端不硬编码生产域名。`NEXT_PUBLIC_WEBCHAT_ENDPOINT` 为必填环境变量，本地和默认部署配置为上述同源代理路径，需要直连时可改为完整 URL。全局适配器把当前登录 Token 作为 WebChat 的 `apiKey` 传入，由浏览器包发送 `Authorization: Bearer <token>`。用户身份由后端根据 Token 解析，不信任 `customData.userId` 作为鉴权依据。

## 接入方式

采用 WebChat 已提供的 UMD 浏览器包，不把 React 组件源码复制进 `web/`，也不重构 npm/pnpm workspace。

- WebChat 浏览器构建产物随 `bklite_web` 静态资源交付。
- 控制台根壳新增一个 app-local 全局适配器，负责资格判断、资源加载和初始化。
- 适配器使用 `sseUrl`，不使用当前源码已弃用且不消费的 `socketUrl`。
- WebChat 保持独立 React 根，避免与 `web/` 的 React 19 依赖和锁文件耦合。

## 展示与权限门禁

适配器同时满足以下条件才加载 WebChat JavaScript 并初始化：

1. 当前用户已登录且登录 Token 可用。
2. `ClientProvider` 已完成全局应用列表加载。
3. 用户可访问的应用列表中存在 `name === "opspilot"`。

未登录、应用列表仍在加载、用户没有 OpsPilot 应用权限或标准布局已卸载时，不显示悬浮按钮，也不调用 Chatflow 接口。报表渲染专用路由继续走现有隔离布局，不加载 WebChat。

权限判断使用全局应用列表，不使用当前路由的 `hasPermission()`；后者只表达当前业务模块内的菜单权限，不能可靠判断用户在其他页面是否拥有 OpsPilot 应用权限。

## 外观

悬浮入口固定在视口右下角。通过 `bklite_web` 的局部覆盖样式适配现有设计系统：

- 使用 BK-Lite 语义色变量和蓝色主操作色。
- 跟随根节点 `.dark` 状态切换亮色与暗色。
- 去掉 WebChat 默认紫色渐变、持续脉冲和夸张放大效果。
- 保留清晰的 hover、focus、disabled 和加载状态。
- 样式限定在 WebChat 根容器内，不覆盖其他 Ant Design 组件。

本次不重做聊天内部的信息架构、交互和文案。

## 生命周期与失败处理

- 同一页面生命周期内只初始化一次，避免路由切换产生多个 `#webchat-root`。
- JavaScript 和样式资源都加载成功后才初始化；任一资源失败时保持隐藏，并显示不含 Token 的通用加载失败提示。
- 接口错误交由 WebChat 现有错误状态展示，控制台页面不被阻断。
- 用户退出登录或适配器卸载时调用 UMD 包的 `destroy()` 卸载 React 根并移除容器，同时终止活跃流和事件监听。

## 验证

至少覆盖以下行为：

- 未登录不加载、不显示。
- 无 OpsPilot 应用权限不加载、不显示。
- 有权限且 Token 可用时只初始化一次，并使用同源代理地址和当前 Token。
- 路由切换后仍只有一个悬浮入口。
- 亮色和暗色主题下入口、面板和交互状态可读。
- 指定 Chatflow 能返回 SSE 流式响应。
- `web/` 的 lint 与类型检查通过；WebChat 静态资源可被生产构建包含。

## 非目标

- 不修改 `sessionId` / `session_id` 字段。
- 不修改 OpsPilot 后端鉴权、Bot 或 Chatflow 配置。
- 不新增聊天应用选择器、会话列表或全局配置页面。
- 不把 WebChat 提升为 `web/src/components` 共享组件。
