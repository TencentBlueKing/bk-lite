/**
 * Bot 管理相关 API
 */
import { apiGet } from './request';

/**
 * 获取 Bot 列表
 */
export const getBotList = (
  params: {
    page?: number;
    page_size?: number;
    name?: string;
    bot_type?: number;
  },
  options?: RequestInit
) => {
  return apiGet<any>('/api/proxy/opspilot/bot_mgmt/bot', params, options);
};