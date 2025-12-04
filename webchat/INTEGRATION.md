# WebChat Integration Examples

## 1. React Application Integration

### Step 1: Install Dependencies

```bash
npm install @webchat/ui @webchat/core
```

### Step 2: Add FloatingButton Component

```jsx
// pages/index.jsx or App.jsx
import React from 'react';
import { FloatingButton } from '@webchat/ui';

export default function Home() {
  return (
    <div>
      <h1>My Application</h1>
      <FloatingButton
        sseUrl="http://localhost:3000/api/chat"
        theme="light"
        title="Support Chat"
        subtitle="We're here to help!"
        placeholder="Type your message..."
        buttonText="Chat with us"
        buttonIcon="💬"
        position="bottom-right"
        customData={{ source: 'website', userId: 'user123' }}
        enableStorage={true}
      />
    </div>
  );
}
```

### Step 3: Create SSE Backend Endpoint

```typescript
// api/chat/stream.ts
import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const headers = new Headers({
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
  });

  const stream = new ReadableStream({
    async start(controller) {
      // Your chat logic here
      const userMessage = new URL(request.url).searchParams.get('message');
      
      controller.enqueue(`data: ${JSON.stringify({
        id: `msg_${Date.now()}`,
        type: 'text',
        content: `You said: ${userMessage}`,
        sender: 'bot',
        timestamp: Date.now(),
      })}\n\n`);

      controller.close();
    },
  });

  return new NextResponse(stream, { headers });
}
```

## 2. HTML/Vanilla JS Integration

Create an HTML file and add the script injection:

```html
<!DOCTYPE html>
<html>
<head>
  <title>My Website</title>
</head>
<body>
  <h1>Welcome to My Website</h1>
  <p>Your website content here...</p>

  <!-- WebChat Integration -->
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
              sseUrl: "http://localhost:3000/api/chat",
              title: "Support",
              theme: "light",
              customData: { page: document.title }
            },
            null  // null = 浮动按钮模式
          );
        }
      }),
      (s.onerror = () => {
        console.error("Failed to load WebChat");
      }),
      t.appendChild(s);
    })();
  </script>
</body>
</html>
```

## 3. Next.js App Router Integration

```tsx
// app/layout.tsx
import { FloatingButton } from '@webchat/ui';
import '@webchat/ui/styles/chat.css';
import '@webchat/ui/styles/floating-button.css';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        {children}
        <FloatingButton
          sseUrl="http://localhost:3000/api/chat"
          theme="light"
          title="Help"
          position="bottom-right"
        />
      </body>
    </html>
  );
}
```

## 4. Vue Integration (using Web Components)

```vue
<template>
  <div>
    <h1>Vue App with WebChat</h1>
    <!-- WebChat will be rendered as Web Component -->
  </div>
</template>

<script>
export default {
  mounted() {
    // Dynamically load WebChat CSS
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://cdn.example.com/webchat/dist/browser/style.css';
    document.head.appendChild(link);
    
    // Dynamically load WebChat JS
    const script = document.createElement('script');
    script.src = 'https://cdn.example.com/webchat/dist/browser/webchat.js';
    script.async = true;
    script.onload = () => {
      if (window.WebChat && window.WebChat.default) {
        window.WebChat.default({
          sseUrl: 'http://localhost:3000/api/chat',
          theme: 'dark'
        }, null);
      }
    };
    document.head.appendChild(script);
  }
};
</script>
```

## 5. Advanced Configuration

### Custom Styling

```tsx
import { FloatingButton } from '@webchat/ui';

export default function App() {
  return (
    <>
      <style>{`
        .floating-button {
          background: linear-gradient(45deg, #667eea, #764ba2);
        }
        
        .webchat-container {
          font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        .webchat-message.message-user .webchat-message-content {
          background: #667eea;
        }
      `}</style>
      
      <FloatingButton
        sseUrl="http://localhost:3000/api/chat"
        customData={{
          brand: 'MyBrand',
          apiVersion: 'v1'
        }}
      />
    </>
  );
}
```

### Event Handling

```tsx
import { FloatingButton } from '@webchat/ui';
import { ChatState, Message } from '@webchat/core';

export default function App() {
  const handleStateChange = (state: ChatState) => {
    console.log('Chat state changed to:', state);
    // Track analytics, update UI, etc.
  };

  const handleMessageReceived = (message: Message) => {
    console.log('Message received:', message);
    // Process message, update backend records, etc.
  };

  const handleError = (error: Error) => {
    console.error('Chat error:', error);
    // Show error notification, log to monitoring service
  };

  return (
    <FloatingButton
      sseUrl="http://localhost:3000/api/chat"
      onStateChange={handleStateChange}
      onMessageReceived={handleMessageReceived}
      onError={handleError}
    />
  );
}
```

## 6. Backend Implementation Examples

### With Rasa NLU

```python
# FastAPI integration with Rasa
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import json

app = FastAPI()

@app.get("/api/chat/stream")
async def chat_stream(message: str, session_id: str):
    async def generate():
        # Send to Rasa
        rasa_response = await call_rasa(message, session_id)
        
        # Stream response
        for text in rasa_response.split(' '):
            yield f"data: {json.dumps({'type': 'text', 'content': text, 'sender': 'bot'})}\n\n"
            await asyncio.sleep(0.1)  # Simulate streaming
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )
```

### With Express.js

```javascript
// Express.js implementation
app.get('/api/chat/stream', (req, res) => {
  const { message, sessionId } = req.query;

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('Access-Control-Allow-Origin', '*');

  // Process message
  const botResponse = processMessage(message, sessionId);

  // Stream response
  let wordIndex = 0;
  const interval = setInterval(() => {
    if (wordIndex < botResponse.length) {
      const msg = {
        type: 'text',
        content: botResponse[wordIndex],
        sender: 'bot',
        timestamp: Date.now()
      };
      res.write(`data: ${JSON.stringify(msg)}\n\n`);
      wordIndex++;
    } else {
      res.write('event: done\ndata: {}\n\n');
      clearInterval(interval);
      res.end();
    }
  }, 100);
});
```

## 7. Analytics Integration

```tsx
import { FloatingButton } from '@webchat/ui';

export default function App() {
  const handleStateChange = (state: string) => {
    // Track to analytics
    window.gtag?.('event', 'chat_state_change', {
      state,
      timestamp: new Date().toISOString()
    });
  };

  const handleMessageReceived = (message: any) => {
    // Track messages
    window.gtag?.('event', 'chat_message', {
      messageType: message.type,
      sender: message.sender,
      timestamp: new Date().toISOString()
    });
  };

  return (
    <FloatingButton
      sseUrl="http://localhost:3000/api/chat"
      onStateChange={handleStateChange}
      onMessageReceived={handleMessageReceived}
    />
  );
}
```

## 8. Multi-language Support

```tsx
const TRANSLATIONS = {
  en: {
    title: 'Support',
    placeholder: 'Type your message...',
  },
  es: {
    title: 'Soporte',
    placeholder: 'Escribe tu mensaje...',
  },
  zh: {
    title: '支持',
    placeholder: '输入您的消息...',
  },
};

export default function App({ lang = 'en' }) {
  const t = TRANSLATIONS[lang] || TRANSLATIONS.en;

  return (
    <FloatingButton
      sseUrl="http://localhost:3000/api/chat"
      title={t.title}
      placeholder={t.placeholder}
      customData={{ language: lang }}
    />
  );
}
```

## 9. Testing

```typescript
// test.spec.ts
import { render, screen, fireEvent } from '@testing-library/react';
import { FloatingButton } from '@webchat/ui';

describe('FloatingButton', () => {
  it('should render floating button', () => {
    render(<FloatingButton sseUrl="http://localhost:3000/api/chat" />);
    const button = screen.getByRole('button');
    expect(button).toBeInTheDocument();
  });

  it('should toggle chat panel on click', () => {
    render(<FloatingButton sseUrl="http://localhost:3000/api/chat" />);
    const button = screen.getByRole('button');
    fireEvent.click(button);
    // Assert chat panel is visible
  });
});
```

## 10. Deployment Checklist

- [ ] Build UMD bundle: `npm run build:ui`
- [ ] Deploy to CDN
- [ ] Update CDN URL in integration script
- [ ] Configure CORS on backend
- [ ] Test in production environment
- [ ] Monitor WebChat errors
- [ ] Set up analytics tracking
- [ ] Document integration for team
- [ ] Create fallback if script fails to load
- [ ] Performance test with multiple concurrent users
