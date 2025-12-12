/**
 * Bot 管理相关 API
 */
import { apiGet } from './request';
import { getTokenSync } from '@/utils/secureStorage';
import { AIChatEvent } from '@/types/conversation';

const TARGET_SERVER = 'http://10.10.40.117:8000/api/v1';

/**
 * 获取应用列表
 */
export const getApplication = (
  params: {
    app_name?: string;
    bot?: number;
    app_tags?: string;
    ordering?: string;
    search?: string;
    page?: number;
    page_size?: number;
  },
  options?: RequestInit
) => {
  return apiGet<any>('/api/proxy/opspilot/bot_mgmt/chat_application/', { app_type: 'mobile', ...params }, options);
}

/**
 * 获取应用详情
 */
export const getApplicationDetail = (
  id: string | number,
  options?: RequestInit
) => {
  return apiGet<any>(`/api/proxy/opspilot/bot_mgmt/chat_application/${id}/`, options);
}

/** 
 * AI 对话 - SSE 流式接口
 * 返回一个异步生成器，用于处理流式事件
 */
export async function* aiChatStream(
  bot: number,
  node_id: string,
  message: string,
  session_id?: string
): AsyncGenerator<AIChatEvent, void, unknown> {
  const token = getTokenSync();
  const url = `${TARGET_SERVER}/opspilot/bot_mgmt/execute_chat_flow/${bot}/${node_id}/`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
      ...(token && { Authorization: `Bearer ${token}` }),
    },
    body: JSON.stringify({ message, ...(session_id && { session_id }) }),
  });

  if (!response.ok) {
    throw new Error(`AI Chat API Error: ${response.status}`);
  }

  // 检查响应类型，如果是 JSON 错误响应则直接处理
  const contentType = response.headers.get('content-type') || '';

  // 如果返回的是 JSON 而不是 SSE 流，可能是错误响应
  if (contentType.includes('application/json')) {
    const jsonResponse = await response.json();
    // 检查是否是错误响应
    if (jsonResponse.result === false || jsonResponse.error) {
      throw new Error(jsonResponse.error || '服务器返回错误');
    }
    // 如果是其他 JSON 响应，也抛出错误（因为期望的是 SSE 流）
    throw new Error('服务器返回了非预期的响应格式');
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('Response body is not readable');
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let hasReceivedValidEvent = false;

  try {
    while (true) {
      const { done, value } = await reader.read();

      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // 按行分割处理 SSE 数据
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // 保留最后一个不完整的行

      for (const line of lines) {
        const trimmedLine = line.trim();

        // 跳过空行和注释
        if (!trimmedLine || trimmedLine.startsWith(':')) continue;

        // 解析 SSE 数据行
        if (trimmedLine.startsWith('data:')) {
          const jsonStr = trimmedLine.slice(5).trim();

          // 跳过 [DONE] 标记
          if (jsonStr === '[DONE]') {
            continue;
          }

          if (jsonStr) {
            try {
              const parsed = JSON.parse(jsonStr);

              // 检查是否是错误响应格式 (result: false 或有 error 字段)
              if (parsed.result === false || (parsed.error && !parsed.type) || parsed.type === 'ERROR' || parsed.type === 'RUN_ERROR') {
                throw new Error(parsed.error || parsed.message || 'Server returned an error');
              }

              // 正常的事件
              hasReceivedValidEvent = true;
              yield parsed as AIChatEvent;
            } catch (e) {
              // 如果是我们自己抛出的 Error，继续向上抛出
              if (e instanceof Error && e.message) {
                throw e;
              }
              console.warn('Failed to parse SSE event:', jsonStr, e);
            }
          }
        }
      }
    }

    // 处理剩余的缓冲区
    if (buffer.trim()) {
      const trimmedLine = buffer.trim();
      if (trimmedLine.startsWith('data:')) {
        const jsonStr = trimmedLine.slice(5).trim();

        // 跳过 [DONE] 标记
        if (jsonStr === '[DONE]') {
          // do nothing
        } else if (jsonStr) {
          try {
            const parsed = JSON.parse(jsonStr);

            // 检查是否是错误响应格式
            if (parsed.result === false || (parsed.error && !parsed.type)) {
              throw new Error(parsed.error || 'Server returned an error');
            }

            hasReceivedValidEvent = true;
            yield parsed as AIChatEvent;
          } catch (e) {
            if (e instanceof Error && e.message) {
              throw e;
            }
            console.warn('Failed to parse final SSE event:', jsonStr, e);
          }
        }
      }
    }

    // 如果整个流程没有收到任何有效事件，抛出错误
    if (!hasReceivedValidEvent) {
      throw new Error('未收到有效的 AI 响应');
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * 获取会话列表
 */
export const getSessions = (
  entry_type = 'mobile'
) => {
  return apiGet<any>(
    '/api/proxy/opspilot/bot_mgmt/chat_application/web_chat_sessions/',
    { entry_type }
  );
}

/**
 * 获取会话历史消息
 */
export const getSessionMessages = (
  sessionId: string,
) => {
  return apiGet<any>(
    '/api/proxy/opspilot/bot_mgmt/chat_application/session_messages/',
    { session_id: sessionId },
  );
}

/**
 * 获取引导语
 */
export const getWelcomeMessage = (
  bot_id: number,
  node_id: string
) => {
  return apiGet<any>(
    '/api/proxy/opspilot/bot_mgmt/chat_application/skill_guide/',
    { bot_id, node_id }
  );
}