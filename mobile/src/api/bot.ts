/**
 * Bot 管理相关 API
 */
import { apiGet, apiPost, apiStream } from './request';
import { AIChatEvent, SessionItem } from '@/types/conversation';

interface ApiResult<T> {
  result: boolean;
  data?: T;
  message?: string;
}

export interface ChatApplicationItem {
  id: number;
  bot: number;
  node_id: string;
  app_name: string;
  app_description?: string;
  app_tags?: string[];
  lastMessage?: string;
}

interface PaginatedApplicationData {
  items?: ChatApplicationItem[];
}

export type ApplicationResult = ApiResult<ChatApplicationItem[] | PaginatedApplicationData>;

export interface GetApplicationsParams {
  app_name?: string;
  bot?: number;
  app_tags?: string;
  ordering?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

/**
 * 获取应用列表
 */
export const getApplication = (
  params: GetApplicationsParams,
  options?: RequestInit
) => {
  return apiGet<ApplicationResult>('/opspilot/bot_mgmt/chat_application/', { app_type: 'mobile', ...params }, options);
}

export function getApplicationItems(result: ApplicationResult): ChatApplicationItem[] {
  if (Array.isArray(result.data)) {
    return result.data;
  }
  return result.data?.items || [];
}

/**
 * 获取应用详情
 */
export const getApplicationDetail = (
  id: string | number,
  options?: RequestInit
) => {
  return apiGet<ApiResult<ChatApplicationItem>>(`/opspilot/bot_mgmt/chat_application/${id}/`, options);
}

/** 
 * AI 对话 - SSE 流式接口
 * 返回一个异步生成器，用于处理流式事件
 */
export async function* aiChatStream(
  bot: number,
  node_id: string,
  message: string | Array<any>,
  session_id?: string,
  options?: RequestInit,
): AsyncGenerator<AIChatEvent, void, unknown> {
  const endpoint = `/opspilot/bot_mgmt/execute_chat_flow/${bot}/${node_id}/`;
  const data = { message, ...(session_id && { session_id }) };

  yield* apiStream<AIChatEvent>(endpoint, data, options);
}

export interface MobileSessionPage {
  count: number;
  items: SessionItem[];
}

export interface GetMobileSessionsParams {
  bot_id?: string | number;
  node_id?: string;
  page?: number;
  page_size?: number;
}

/**
 * 分页获取 Mobile 会话列表
 */
export const getMobileSessions = (
  params: GetMobileSessionsParams = {},
  options?: RequestInit
) => {
  return apiGet<ApiResult<MobileSessionPage>>(
    '/opspilot/bot_mgmt/chat_application/mobile_sessions/',
    params,
    options
  );
}

/**
 * 删除当前用户的指定会话历史
 */
export const deleteSessionHistory = (
  node_id: string,
  session_id: string,
  options?: RequestInit
) => {
  return apiPost<ApiResult<null>>(
    '/opspilot/bot_mgmt/chat_application/delete_session_history/',
    { node_id, session_id },
    options
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
    '/opspilot/bot_mgmt/chat_application/session_messages/',
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
    '/opspilot/bot_mgmt/chat_application/skill_guide/',
    { bot_id, node_id },
    options
  );
}
