# OpsPilot ChatFlow 接入文档

触发方式是启动一个 Chatflow（聊天工作流）的"开关"。选择不同的触发方式，决定了工作流如何启动、由谁启动以及适用的场景。**定时触发、RESTful API、OpenAI API、AG-UI**这些方式相辅相成，使得 Chatflow 能够适应从简单自动化到复杂系统集成的各种需求。

## 触发方式1：定时触发

定时触发是自动化工作流中非常强大和常用的一种触发方式。它允许您的工作流（Chatflow）在**特定的时间点**或按照**固定的时间间隔**自动启动运行，而无需任何人工手动操作。是用一个时间计划（类似于闹钟或 cron 作业）来作为启动工作流的“开关”。当系统时间满足您预设的条件时，系统就会自动创建一个新的工作流实例并开始执行。无论是简单的日常提醒，还是复杂的数据处理任务，定时触发都能为您提供精准、可靠、高效的自动化启动方案，让工作流如同瑞士钟表般精准运行，成为企业数字化转型中不可或缺的自动化基石。

## 触发方式2：RESTful API

RESTful API 允许将工作流（Chatflow）**发布为一个标准的 API 接口**，从而可以被任何能够发送 HTTP 请求的系统、应用或服务所调用。简单来说，它是为 Chatflow 生成一个唯一的 URL 地址（通常称为 **Webhook URL** 或 **Endpoint**）。拥有这个chatflow工作台权限的用户发起post请求，都会立即触发该 Chatflow 的执行。RESTful API 触发不仅是一个技术功能，更是企业数字化转型的战略性接口。它将工作流从封闭的自动化工具升级为开放的数字业务枢纽，让每一个创意都能快速连接世界，让每一次创新都能轻松整合资源。

示例：

body传递参数：{"user_message": "帮我检查下服务器状态"}

RESTful API请求地址：<http://bklite.canwya.net/api/v1/opspilot/bot_mgmt/execute_chat_flow/?bot_id=1&node_id=abcdef>

（触发节点的请求地址，请在画布保存后在对应节点查看）

## 触发方式3：OpenAI API

OpenAI API本质上是将 Chatflow 直接挂载到 **OpenAI 的模型生态系统**中，允许通过调用 OpenAI 的 API（如 ChatGPT, GPT-4）来触发并运行工作流。简单来说，它允许创建一个**自定义的 GPT 动作（Action）**或 一个**可供 OpenAI API 调用的专用模型**。当用户与 GPT 对话时，或者在代码中调用特定的 OpenAI 模型时，其请求不会被发送到通用的 ChatGPT，而是被路由到预先设计好的 Chatflow 中。Chatflow 处理完请求后，再将结果返回，由 OpenAI 呈现给用户。OpenAI API 触发不仅仅是一个技术功能，更是企业进入AI原生时代的关键入口。它将专业能力转化为AI可理解和执行的数字服务，让每个企业都能拥有一个7×24小时不眠不休的智能员工团队。

示例：

body传递参数：{"user_message": "帮我检查下服务器状态"}

OpenAI API请求地址：<http://bklite.canwya.net/api/v1/opspilot/bot_mgmt/execute_chat_flow/?bot_id=1&node_id=abcdef>

（触发节点的请求地址，请在画布保存后在对应节点查看）

## 触发方式4：AG-UI

AG-UI（Agent User Interface）触发方式是专为智能体对话界面设计的触发机制，它将 Chatflow 无缝集成到 **AG-UI 对话系统**中，使得用户可以通过统一的智能体界面与工作流进行自然语言交互。简单来说，它是为 Chatflow 创建一个**专属的对话入口**，当用户在 AG-UI 界面中发起对话时，系统会自动路由到对应的 Chatflow 进行处理。AG-UI 触发方式的核心优势在于提供了一致的用户体验和智能化的交互方式，让用户无需关心底层的工作流逻辑，只需通过自然对话即可完成复杂的业务操作。这种触发方式特别适合需要频繁人机交互、对用户体验要求较高的场景。AG-UI 触发不仅仅是一个技术接口，更是企业打造智能化服务体验的重要桥梁。它将复杂的工作流封装为简单的对话交互，让每个员工都能像与同事聊天一样轻松使用企业的自动化能力，真正实现AI驱动的数字化转型。

示例：

body传递参数：{"user_message": "帮我检查下服务器状态"}

AG-UI请求地址：<http://bklite.canwya.net/api/v1/opspilot/bot_mgmt/execute_chat_flow/?bot_id=1&node_id=abcdef>

（触发节点的请求地址，请在画布保存后在对应节点查看）

## 触发方式5：嵌入式对话

嵌入式对话触发方式是基于 **AG-UI 协议**的网页嵌入式对话窗口，它允许您将 Chatflow 以**对话组件**的形式直接嵌入到任何网页中，为网站访客提供即时的智能对话服务。通过简单的 JavaScript 代码片段，即可在网页的任意位置或以浮动按钮的形式展示对话窗口，用户点击后即可与 Chatflow 进行实时交互。这种触发方式特别适合企业官网、产品页面、在线文档、内部系统等需要提供实时客户支持或智能助手服务的场景。嵌入式对话不仅降低了接入门槛，更提供了灵活的样式定制和数据传递能力，让企业能够在保持品牌一致性的同时，为用户提供流畅的对话体验。嵌入式对话触发是企业构建智能化用户服务体系的前端入口，它将强大的工作流能力以最友好的方式呈现给最终用户，真正实现"所见即所得"的智能化服务体验。

### 嵌入代码示例

将以下代码添加到您的网页 HTML 中（建议放在 `</body>` 标签之前）：

```html
<script>
  !(function () {
    let e = document.createElement("link"),
      s = document.createElement("script"),
      t = document.head || document.getElementsByTagName("head")[0];
    
    // 加载样式
    (e.rel = "stylesheet"),
    (e.href = "https://cdn.example.com/webchat/dist/browser/style.css"),
    t.appendChild(e);
    
    // 加载脚本
    (s.src = "https://cdn.example.com/webchat/dist/browser/webchat.js"),
    (s.async = !0),
    (s.onload = () => {
      if (window.WebChat && window.WebChat.default) {
        window.WebChat.default(
          {
            sseUrl: "http://bklite.canwya.net/api/v1/opspilot/bot_mgmt/execute_chat_flow/?bot_id=1&node_id=abcdef",
            title: "智能助手",
            theme: "light",  // 可选: light / dark
            customData: { page: document.title }
          },
          null  // null = 浮动按钮模式，或传入 DOM 元素实现内联嵌入
        );
      }
    }),
    (s.onerror = () => {
      console.error("Failed to load WebChat");
    }),
    t.appendChild(s);
  })();
</script>
```

### 配置说明

- **sseUrl**: Chatflow 的 SSE 流式请求地址（触发节点的请求地址，请在画布保存后在对应节点查看）
- **title**: 对话窗口标题
- **theme**: 主题样式，支持 `light`（浅色）或 `dark`（深色）
- **customData**: 自定义数据，会随请求发送到 Chatflow
- **第二个参数**: 
  - `null` - 以浮动按钮形式显示在页面右下角
  - DOM 元素 - 将对话窗口内联嵌入到指定的 HTML 元素中

### 使用场景

- 企业官网的在线客服
- 产品文档的智能问答助手
- 内部系统的操作引导
- 电商网站的购物咨询
- SaaS 产品的用户支持
