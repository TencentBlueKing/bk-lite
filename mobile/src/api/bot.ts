/**
 * Bot 管理相关 API
 */
import { apiGet, apiStream } from './request';
import { AIChatEvent } from '@/types/conversation';

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
  message: string | Array<any>,
  session_id?: string
): AsyncGenerator<AIChatEvent, void, unknown> {
  const endpoint = `/api/proxy/opspilot/bot_mgmt/execute_chat_flow/${bot}/${node_id}/`;
  const data = { message, ...(session_id && { session_id }) };

  yield* apiStream<AIChatEvent>(endpoint, data);
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
  options?: RequestInit
) => {
  return apiGet<any>(
    '/api/proxy/opspilot/bot_mgmt/chat_application/session_messages/',
    { session_id: sessionId },
    options
  );
}

/**
 * 获取引导语
 */
export const getWelcomeMessage = (
  bot_id: number,
  node_id: string,
  options?: RequestInit
) => {
  return apiGet<any>(
    '/api/proxy/opspilot/bot_mgmt/chat_application/skill_guide/',
    { bot_id, node_id },
    options
  );
}