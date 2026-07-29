# WebChat - Modern Web Chat Library

A modern, modular web chat library inspired by Rasa-web with support for SSE streaming, session management, and flexible deployment options.

## ✨ Features

- 🎯 **Floating Button Integration** - Easy one-line script injection
- 🔄 **SSE Streaming** - Real-time message streaming with Server-Sent Events
- 💾 **Session Management** - Automatic session persistence and recovery
- 🎨 **Customizable UI** - Light/dark themes and full styling control
- 📱 **Responsive Design** - Works seamlessly on desktop and mobile
- ⚙️ **State Machine** - Robust conversation flow management
- 🔌 **Flexible Integration** - React components, UMD bundle, or vanilla JS
- 🚀 **Production Ready** - TypeScript, proper error handling, and retry logic

## 📦 Project Structure

```
webchat/
├── packages/
│   ├── webchat-core/          # Core logic (no UI framework dependency)
│   │   ├── types.ts           # Type definitions
│   │   ├── sessionManager.ts   # Session management
│   │   ├── stateMachine.ts     # State machine for chat flow
│   │   ├── sse.ts             # SSE handler with auto-reconnect
│   │   └── utils.ts           # Utility functions
│   │
│   ├── webchat-ui/            # React UI components
│   │   ├── Chat.tsx           # Main chat component
│   │   ├── FloatingButton.tsx  # Floating button component
│   │   └── styles/            # CSS styles
│   │
│   └── webchat-demo/          # Next.js demo application
│       ├── app/               # Next.js App Router
│       ├── api/chat/          # SSE API endpoints
│       └── public/            # Static assets
│
├── build/                     # Build configurations
├── .github/                   # CI/CD workflows
└── README.md
```

## 🚀 Quick Start

### 方式一：浏览器直接引入（最简单）

在任何 HTML 页面中引入构建好的文件：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WebChat 示例</title>
    
    <!-- 引入 WebChat CSS -->
    <link rel="stylesheet" href="./packages/webchat-ui/dist/browser/style.css">
    <!-- 引入 WebChat JS (已包含 React) -->
    <script src="./packages/webchat-ui/dist/browser/webchat.js"></script>
</head>
<body>
    <h1>WebChat 浮动按钮示例</h1>
    <p>页面加载后会自动出现右下角的聊天按钮，点击即可开始聊天。</p>

    <script>
        // 最简单的方式：一行代码初始化
        window.WebChat.default({
            sseUrl: 'http://your-backend-api/chat',
            title: '智能助手',
            botAvatarUrl: 'https://api.dicebear.com/7.x/bottts/svg?seed=bot',
            userAvatarUrl: 'https://api.dicebear.com/7.x/avataaars/svg?seed=user',
            customData: { type: 'agui' },
            showFullscreenButton: true,
            showClearButton: true
        });
    </script>
</body>
</html>
```

### 方式二：React 项目中使用

### 方式二：React 项目中使用

```tsx
import React from 'react';
import { FloatingButton } from '@webchat/ui';

export default function App() {
  return (
    <>
      <div>Your app content</div>
      <FloatingButton
        sseUrl="http://your-backend-api/chat"
        theme="light"
        title="Support Chat"
        subtitle="We're here to help!"
        showFullscreenButton={true}
        showClearButton={true}
      />
    </>
  );
}
```

### 方式三：CDN 引入（推荐生产环境）

### 方式三：CDN 引入（推荐生产环境）

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <link rel="stylesheet" href="https://cdn.example.com/webchat/dist/browser/style.css">
</head>
<body>
  <h1>您的网站内容</h1>
  
  <!-- WebChat 集成脚本 -->
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
        window.WebChat.default({
          sseUrl: "http://your-backend-api/chat",
          title: "在线客服",
          botAvatarUrl: "https://your-cdn.com/bot-avatar.png",
          userAvatarUrl: "https://your-cdn.com/user-avatar.png",
          customData: { 
            userId: "user123",
            source: "website"
          },
          showFullscreenButton: true,
          showClearButton: true
        }, null);
      }),
      t.appendChild(s);
    })();
  </script>
</body>
</html>
```

### 开发构建

```bash
# 安装依赖
npm install

# 构建所有包
npm run build

# 启动演示应用
npm run dev
```

## 📝 配置参数

### 核心配置项

```typescript
interface WebChatConfig {
  sseUrl?: string;                  // SSE 服务端点 URL（必填）
  customData?: Record<string, any>;     // 随请求发送的自定义元数据
  extensions?: Record<string, unknown>; // 集成方自用扩展，不随请求发送
  title?: string;                   // 聊天窗口标题，默认：'Chat'
  subtitle?: string;                // 聊天窗口副标题
  placeholder?: string;             // 输入框占位符，默认：'Type a message...'
  
  // 外观配置
  botAvatarUrl?: string;            // 机器人头像 URL
  userAvatarUrl?: string;           // 用户头像 URL
  showFullscreenButton?: boolean;   // 显示全屏按钮，默认：true
  showClearButton?: boolean;        // 显示清空按钮，默认：false
  
  // 存储配置
  enableStorage?: boolean;          // 启用会话持久化，默认：true
  storageKey?: string;              // localStorage 存储键，默认：'webchat_session'
  
  // 回调函数
  onStateChange?: (state: ChatState) => void;
  onMessageReceived?: (message: Message) => void;
  onError?: (error: Error) => void;
  onClose?: () => void;
}
```

### 旧配置迁移

`socketUrl` 仅为 `sseUrl` 的兼容别名；两者同时提供时以 `sseUrl` 为准。`socketPath`、`enableSSE`、`reconnectAttempts`
和 `reconnectDelay` 不再控制当前基于单次 fetch 流的 UI，类型中只为旧调用保留并标记为 deprecated。

自定义集成配置请放到 `extensions`，需要随聊天请求发送的数据仍放到 `customData`：

```typescript
const config: WebChatConfig = {
  sseUrl: 'https://example.com/api/chat',
  extensions: {
    pluginMode: 'compact',
  },
  customData: {
    source: 'website',
  },
};
```

### 浮动按钮额外配置

```typescript
interface FloatingButtonProps extends ChatProps {
  buttonText?: string;              // 按钮文字，默认：'聊天'
  position?: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left';
  // 默认：'bottom-right'
}
```

## 🏗️ 架构说明

### 消息格式（AG-UI 协议）

支持流式传输的 AG-UI 协议：

```json
// TEXT_MESSAGE_START - 开始新消息
{
  "type": "TEXT_MESSAGE_START",
  "messageId": "msg_1234567890_abc123",
  "timestamp": 1234567890
}

// TEXT_MESSAGE_CONTENT - 流式内容块
{
  "type": "TEXT_MESSAGE_CONTENT",
  "messageId": "msg_1234567890_abc123",
  "delta": "Hello! ",
  "timestamp": 1234567890
}

// TEXT_MESSAGE_END - 消息结束
{
  "type": "TEXT_MESSAGE_END",
  "messageId": "msg_1234567890_abc123",
  "timestamp": 1234567890
}

// RUN_FINISHED - 对话完成
{
  "type": "RUN_FINISHED",
  "timestamp": 1234567890
}
```

### 会话存储

会话自动存储在 localStorage 中，支持页面刷新后恢复对话：

```json
{
  "sessionId": "session_1234567890_abc123",
  "messages": [
    {
      "id": "msg_user_123",
      "type": "text",
      "content": "Hello",
      "sender": "user",
      "timestamp": 1234567890
    },
    {
      "id": "msg_bot_456",
      "type": "text",
      "content": "Hi! How can I help?",
      "sender": "bot",
      "timestamp": 1234567891
    }
  ],
  "customData": {
    "userId": "user123",
    "source": "website"
  },
  "lastActivityTime": 1234567891
}
```

### 支持的消息类型

- `text` - 纯文本消息
- `markdown` - Markdown 格式消息（支持 GFM）
- 流式消息实时渲染
- 工具调用状态显示

## 🎯 Core Classes

### SessionManager

Manages chat sessions and persistence:

```typescript
const manager = new SessionManager(config);
const session = manager.initSession(userId);
manager.addMessage(message);
const messages = manager.getMessages();
manager.clearSession();
```

### StateMachine

Controls chat state transitions:

```typescript
const machine = new StateMachine('idle');
machine.transition('connecting');
machine.on((event) => {
  console.log(`State changed from ${event.from} to ${event.to}`);
});
```

### SSEHandler

Handles Server-Sent Events:

```typescript
const handler = new SSEHandler(5, 1000); // maxAttempts, delay
handler.connect(url);
handler.on('message', (event) => {
  console.log(event.message);
});
```

## 🛠️ Development

### Build

```bash
# Build all packages
npm run build

# Build specific package
npm run build:core
npm run build:ui
npm run build:demo

# Watch mode
cd packages/webchat-core && npm run dev
```

### Development Server

```bash
# Start Next.js demo with hot reload
npm run dev

# Opens at http://localhost:3000
```

### Testing

```bash
npm run test
npm run lint
```

## 📦 Publishing

### npm Registry

```bash
# Build all packages
npm run build

# Publish to npm
cd packages/webchat-core && npm publish
cd packages/webchat-ui && npm publish
```

### CDN Deployment

```bash
# Build UMD bundle
npm run build:ui

# Upload dist/index.umd.js to CDN
# Update integration script with CDN URL
```

## 🔐 Security Considerations

1. **CORS** - Configure CORS headers on backend
2. **XSS Protection** - Content is sanitized
3. **Session** - Use secure session IDs
4. **SSL/TLS** - Use HTTPS in production
5. **Rate Limiting** - Implement on backend

## 🐛 Troubleshooting

### Connection Issues

```typescript
// Check SSE connection
const handler = new SSEHandler();
handler.on('error', (event) => {
  console.error('Connection error:', event.error);
});
```

### Session Not Persisting

```typescript
// Enable storage
enableStorage: true,
storageKey: '@webchat/session'
```

### Messages Not Streaming

```typescript
// Check SSE format in backend response
// Must include: data: {json_message}\n\n
```

## 📄 License

MIT

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines.

## 📞 Support

For issues and questions:
- GitHub Issues: [webchat/issues]
- Email: support@example.com

## 🗺️ Roadmap

- [ ] Voice message support
- [ ] Image upload from client
- [ ] Rich text editor
- [ ] Multi-language support
- [ ] Mobile app (React Native)
- [ ] Analytics integration
- [ ] Rate limiting UI
- [ ] Typing indicators
