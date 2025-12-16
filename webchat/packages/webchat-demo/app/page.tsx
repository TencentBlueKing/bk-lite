import type { Metadata } from 'next';
import { ChatWrapper } from './chat-wrapper';

export const metadata: Metadata = {
  title: 'WebChat Demo',
  description: 'WebChat library demo with floating button and SSE support',
};

export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-indigo-600 via-purple-600 to-purple-700 p-10 sm:p-5 relative overflow-hidden">
      {/* Background Pattern */}
      <div className="absolute inset-0 opacity-10 pointer-events-none" style={{
        backgroundImage: 'radial-gradient(circle, white 1px, transparent 1px)',
        backgroundSize: '50px 50px'
      }} />

      <div className="max-w-4xl mx-auto bg-gradient-to-b from-white to-blue-50 rounded-3xl p-12 sm:p-5 shadow-2xl relative z-10">
        <header className="text-center mb-12 pb-8 border-b-2 border-gray-200">
          <h1 className="m-0 mb-3 text-5xl sm:text-3xl font-black bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
            WebChat Demo
          </h1>
          <p className="m-0 text-base text-gray-600 font-medium">
            Click the floating button in the bottom-right corner to start chatting!
          </p>
        </header>

        <section className="mb-11 pb-8 border-b border-gray-200 last:border-b-0 last:mb-0 last:pb-0">
          <h2 className="m-0 mb-5 text-3xl sm:text-2xl text-gray-900 font-bold">Features</h2>
          <ul className="m-0 pl-6 text-gray-700 leading-loose text-base">
            <li className="mb-3 font-medium">💬 Floating chat button with smooth animations</li>
            <li className="mb-3 font-medium">🔄 Real-time streaming with SSE (Server-Sent Events)</li>
            <li className="mb-3 font-medium">💾 Session persistence and history</li>
            <li className="mb-3 font-medium">🎨 Customizable theme (light/dark mode)</li>
            <li className="mb-3 font-medium">📱 Fully responsive design</li>
            <li className="mb-3 font-medium">⚡ Zero dependencies (except React)</li>
          </ul>
        </section>

        <section className="mb-11 pb-8 border-b border-gray-200 last:border-b-0 last:mb-0 last:pb-0">
          <h2 className="m-0 mb-5 text-3xl sm:text-2xl text-gray-900 font-bold">API Endpoint</h2>
          <p className="mb-3">Connect to: <code className="bg-gradient-to-r from-gray-100 to-blue-50 px-2 py-1 rounded border-l-4 border-indigo-600 font-mono text-purple-600 font-semibold text-sm">http://localhost:3000/api/chat</code></p>
          <p>The chat component will stream responses using Server-Sent Events.</p>
        </section>

        <section className="mb-11 pb-8 border-b border-gray-200 last:border-b-0 last:mb-0 last:pb-0">
          <h2 className="m-0 mb-5 text-3xl sm:text-2xl text-gray-900 font-bold">How to Use</h2>
          <ol className="m-0 pl-6 text-gray-700 leading-loose text-base">
            <li className="mb-3 font-medium">Click the floating chat button (💬) in the bottom-right corner</li>
            <li className="mb-3 font-medium">Type your message and press Enter or click Send</li>
            <li className="mb-3 font-medium">Watch the responses stream in real-time!</li>
          </ol>
        </section>

        <section className="mb-11 pb-8 border-b border-gray-200 last:border-b-0 last:mb-0 last:pb-0">
          <h2 className="m-0 mb-5 text-3xl sm:text-2xl text-gray-900 font-bold">Integration in Other Projects</h2>
          <pre className="bg-gradient-to-br from-gray-900 to-gray-800 text-gray-200 p-6 rounded-lg overflow-x-auto text-sm leading-relaxed m-5 border border-gray-700 shadow-inner">
            {`<script>
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
        sseUrl: "http://your-api:3000/api/chat",
        title: "Support",
        theme: "light"
      }, null);  // null = 浮动按钮模式
    }),
    t.appendChild(s);
  })();
</script>`}
          </pre>
        </section>
      </div>

      {/* Floating Chat Button */}
      <ChatWrapper />
    </main>
  );
}
