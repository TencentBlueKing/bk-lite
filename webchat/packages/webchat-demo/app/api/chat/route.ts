import { NextRequest, NextResponse } from 'next/server';

/**
 * SSE Chat API Route
 * Streams chat responses using Server-Sent Events
 */

export const runtime = 'nodejs';

export async function GET(_request: NextRequest) {
  // Set up SSE headers
  const headers = new Headers({
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  });

  // Create a readable stream
  const stream = new ReadableStream({
    start(controller) {
      let isAlive = true;
      let isClosed = false;

      const safeClose = () => {
        if (!isClosed) {
          try {
            controller.close();
            isClosed = true;
          } catch (e) {
            // Already closed
          }
        }
      };

      // Keep connection alive with periodic heartbeats
      const heartbeatInterval = setInterval(() => {
        if (isAlive && !isClosed) {
          try {
            controller.enqueue(': keep-alive\n\n');
          } catch (e) {
            isAlive = false;
            clearInterval(heartbeatInterval);
            safeClose();
          }
        }
      }, 30000); // 30 second heartbeat

      // Auto-close after 10 minutes
      const timeout = setTimeout(() => {
        if (isAlive && !isClosed) {
          try {
            controller.enqueue('event: done\ndata: {}\n\n');
          } catch (e) {
            // Ignore if already closed
          }
          isAlive = false;
        }
        clearInterval(heartbeatInterval);
        safeClose();
      }, 10 * 60 * 1000);

      // Cleanup
      return () => {
        clearInterval(heartbeatInterval);
        clearTimeout(timeout);
        isAlive = false;
        safeClose();
      };
    },
  });

  return new NextResponse(stream, { headers });
}

/**
 * POST endpoint for sending messages
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { message } = body;

    // For POST, we can also return SSE
    const headers = new Headers({
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'Access-Control-Allow-Origin': '*',
    });

    const stream = new ReadableStream({
      async start(controller) {
        const threadId = `thread_${Date.now()}`;
        const runId = `run_${Date.now()}`;
        const messageId = `msg_${runId}`;
        
        // 1. RUN_STARTED
        controller.enqueue(
          `data: ${JSON.stringify({
            type: 'RUN_STARTED',
            timestamp: Date.now(),
            threadId,
            runId,
          })}\n\n`
        );
        
        await new Promise((resolve) => setTimeout(resolve, 300));
        
        // 2. THINKING_START
        controller.enqueue(
          `data: ${JSON.stringify({
            type: 'THINKING_START',
            timestamp: Date.now(),
          })}\n\n`
        );
        
        await new Promise((resolve) => setTimeout(resolve, 500));
        
        // 3. 第一个工具调用 - get_current_time
        const toolCallId1 = `call_time_${Date.now()}`;
        controller.enqueue(
          `data: ${JSON.stringify({
            type: 'TOOL_CALL_START',
            timestamp: Date.now(),
            toolCallId: toolCallId1,
            toolCallName: 'get_current_time',
            parentMessageId: messageId,
          })}\n\n`
        );
        
        await new Promise((resolve) => setTimeout(resolve, 150));
        
        controller.enqueue(
          `data: ${JSON.stringify({
            type: 'TOOL_CALL_ARGS',
            timestamp: Date.now(),
            toolCallId: toolCallId1,
            delta: '{"timezone":"Asia/Shanghai"}',
          })}\n\n`
        );
        
        await new Promise((resolve) => setTimeout(resolve, 200));
        
        controller.enqueue(
          `data: ${JSON.stringify({
            type: 'TOOL_CALL_END',
            timestamp: Date.now(),
            toolCallId: toolCallId1,
            result: { time: new Date().toLocaleTimeString('zh-CN') },
          })}\n\n`
        );
        
        await new Promise((resolve) => setTimeout(resolve, 100));
        
        // TOOL_CALL_RESULT for tool 1
        const resultId1 = `result_${Date.now()}`;
        controller.enqueue(
          `data: ${JSON.stringify({
            type: 'TOOL_CALL_RESULT',
            timestamp: Date.now(),
            messageId: resultId1,
            toolCallId: toolCallId1,
            content: new Date().toLocaleString('zh-CN'),
            role: 'tool',
          })}\n\n`
        );
        
        await new Promise((resolve) => setTimeout(resolve, 200));
        
        // 4. 第二个工具调用 - search_web
        const toolCallId2 = `call_search_${Date.now()}`;
        controller.enqueue(
          `data: ${JSON.stringify({
            type: 'TOOL_CALL_START',
            timestamp: Date.now(),
            toolCallId: toolCallId2,
            toolCallName: 'search_web',
            parentMessageId: messageId,
          })}\n\n`
        );
        
        await new Promise((resolve) => setTimeout(resolve, 150));
        
        controller.enqueue(
          `data: ${JSON.stringify({
            type: 'TOOL_CALL_ARGS',
            timestamp: Date.now(),
            toolCallId: toolCallId2,
            delta: `{"query":"${message}","limit":3}`,
          })}\n\n`
        );
        
        await new Promise((resolve) => setTimeout(resolve, 400));
        
        controller.enqueue(
          `data: ${JSON.stringify({
            type: 'TOOL_CALL_END',
            timestamp: Date.now(),
            toolCallId: toolCallId2,
            result: { 
              results: [
                { title: '搜索结果1', url: 'https://example.com/1' },
                { title: '搜索结果2', url: 'https://example.com/2' },
              ]
            },
          })}\n\n`
        );
        
        await new Promise((resolve) => setTimeout(resolve, 100));
        
        // TOOL_CALL_RESULT for tool 2
        const resultId2 = `result_${Date.now()}`;
        controller.enqueue(
          `data: ${JSON.stringify({
            type: 'TOOL_CALL_RESULT',
            timestamp: Date.now(),
            messageId: resultId2,
            toolCallId: toolCallId2,
            content: JSON.stringify({
              results: [
                { title: '搜索结果1', url: 'https://example.com/1' },
                { title: '搜索结果2', url: 'https://example.com/2' },
              ]
            }),
            role: 'tool',
          })}\n\n`
        );
        
        await new Promise((resolve) => setTimeout(resolve, 200));
        
        // 5. THINKING_END
        controller.enqueue(
          `data: ${JSON.stringify({
            type: 'THINKING_END',
            timestamp: Date.now(),
          })}\n\n`
        );
        
        await new Promise((resolve) => setTimeout(resolve, 200));
        
        // 6. TEXT_MESSAGE_START
        controller.enqueue(
          `data: ${JSON.stringify({
            type: 'TEXT_MESSAGE_START',
            timestamp: Date.now(),
            messageId,
          })}\n\n`
        );
        
        await new Promise((resolve) => setTimeout(resolve, 100));
        
        // 7. TEXT_MESSAGE_CHUNK - 流式输出文本（包含工具调用结果）
        const currentTime = new Date().toLocaleTimeString('zh-CN');
        const responseText = `我收到了你的消息："${message}"。

我调用了以下工具来帮助你：
1. 🕐 获取当前时间：${currentTime}
2. 🔍 搜索相关信息：找到了 2 条结果

这是使用 AG-UI 协议的模拟回复，展示了完整的工具调用流程和流式文本输出。`;
        
        for (let i = 0; i < responseText.length; i++) {
          controller.enqueue(
            `data: ${JSON.stringify({
              type: 'TEXT_MESSAGE_CHUNK',
              timestamp: Date.now(),
              messageId,
              delta: responseText[i],
            })}\n\n`
          );
          
          // 模拟打字延迟
          await new Promise((resolve) => setTimeout(resolve, 30));
        }
        
        // 8. TEXT_MESSAGE_END
        controller.enqueue(
          `data: ${JSON.stringify({
            type: 'TEXT_MESSAGE_END',
            timestamp: Date.now(),
            messageId,
          })}\n\n`
        );
        
        await new Promise((resolve) => setTimeout(resolve, 200));
        
        // 10. RUN_FINISHED
        controller.enqueue(
          `data: ${JSON.stringify({
            type: 'RUN_FINISHED',
            timestamp: Date.now(),
            threadId,
            runId,
          })}\n\n`
        );
        
        // 发送完成信号
        controller.enqueue('event: done\ndata: {}\n\n');
        controller.close();
      },
    });

    return new NextResponse(stream, { headers });
  } catch (error) {
    console.error('POST error:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

/**
 * Handle CORS preflight
 */
export async function OPTIONS() {
  return new NextResponse(null, {
    status: 200,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    },
  });
}
