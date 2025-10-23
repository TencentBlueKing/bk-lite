/**
 * 认证相关 API
 */
import { apiGet, apiPost } from './request';

/**
 * 获取域名列表
 */
export const getDomainList = () => {
  return apiGet<any>('/api/proxy/core/api/get_domain_list');
};

/**
 * 用户登录
 */
export const authLogin = (params: {
  username: string;
  password: string;
  domain: string;
}) => {
  return apiPost<any>('/api/proxy/core/api/login', params);
};

/**
 * 获取登录信息
 */
export const getLoginInfo = () => {
  return apiGet<any>('/api/proxy/core/api/login_info');
};
