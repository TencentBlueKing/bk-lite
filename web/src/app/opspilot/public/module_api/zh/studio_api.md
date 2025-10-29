# OpsPilot ChatFlow 接入文档

触发方式是启动一个 Chatflow（聊天工作流）的“开关”。选择不同的触发方式，决定了工作流如何启动、由谁启动以及适用的场景。**定时触发、RESTful API、OpenAI API**这三种方式相辅相成，使得 Chatflow 能够适应从简单自动化到复杂系统集成的各种需求。

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
