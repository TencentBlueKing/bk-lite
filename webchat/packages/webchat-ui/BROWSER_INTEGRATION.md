# WebChat 浏览器集成指南

## 快速开始

### 1. 构建浏览器版本

```bash
cd packages/webchat-ui
npm run build:browser
```

这会在 `dist/browser/` 目录生成：
- `webchat.js` - 完整的 UMD 包（~484KB，已包含 React 和所有依赖）
- `style.css` - 样式文件

### 2. 部署文件

将 `dist/browser/` 文件夹上传到你的 CDN 或静态服务器。

### 3. 集成到网页

在你的 HTML 中添加以下代码：

```html
<!-- 引入 WebChat (已包含 React，无需其他依赖) -->
<link rel="stylesheet" href="https://your-cdn.com/webchat/style.css">
<script src="https://your-cdn.com/webchat/webchat.js"></script>

<script>
  // 浮动按钮模式（默认）
  window.WebChat.default({
    sseUrl: 'http://your-api.com/api/chat',
    title: '在线客服',
    buttonText: '💬'
  });
</script>
```

### 4. 嵌入到指定容器

```html
<div id="chat-container" style="height: 600px;"></div>

<script>
  // 渲染到指定容器
  window.WebChat.default({
    sseUrl: 'http://your-api.com/api/chat',
    title: '智能助手'
  }, 'chat-container');  // 传入容器 ID
</script>
```

### 4. 配置选项

```javascript
window.WebChat.default(
  {
    sseUrl: "http://your-api.com/api/chat",  // SSE 接口地址
    title: "在线客服",                        // 聊天窗口标题
    subtitle: "我们随时为您服务",             // 副标题
    placeholder: "请输入消息...",            // 输入框占位符
    theme: "light",                           // 主题：light 或 dark
    customData: {                             // 自定义数据
      userId: "user123",
      sessionId: "session456"
    }
  },
  null  // 元素 ID：null 为浮动按钮，或传入容器 ID 嵌入指定位置
);
```

## 两种使用模式

### 模式 1：浮动按钮（推荐）

```javascript
// elementId 传 null
window.WebChat.default(config, null);
```

效果：页面右下角出现浮动聊天按钮，点击展开聊天窗口。

### 模式 2：嵌入式

```html
<div id="chat-container"></div>

<script>
  window.WebChat.default(config, "chat-container");
</script>
```

效果：聊天界面嵌入到指定的 div 容器中。

## 本地测试

1. 构建浏览器版本：
   ```bash
   cd packages/webchat-ui
   npm run build:browser
   ```

2. 启动测试服务器：
   ```bash
   cd dist
   python3 -m http.server 8080
   ```

3. 打开浏览器访问：
   ```
   http://localhost:8080/test.html
   ```

## 文件说明

- **dist/browser/index.js** - 完整的 UMD 包，包含所有依赖
- **dist/browser/style.css** - CSS 样式
- **dist/test.html** - 测试页面示例

## 注意事项

1. **文件大小**：`index.js` 约 810KB（压缩后 ~248KB），因为包含了 React 和 Ant Design X
2. **浏览器兼容性**：支持现代浏览器（Chrome、Firefox、Safari、Edge）
3. **HTTPS**：在生产环境建议使用 HTTPS 协议
4. **跨域**：确保 SSE API 允许跨域请求（设置 CORS 头）

## 示例代码

完整示例请查看 `dist/test.html` 文件。
