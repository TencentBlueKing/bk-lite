/**
 * 认证相关 API
 */
import type { ExternalLoginResult } from '@/auth/im-login/types';
import { apiGet, apiPost } from './request';

interface LoginResultResponse<T> {
  result?: boolean;
  message?: string;
  data?: T;
}

/**
 * 获取域名列表
 */
export const getDomainList = () => {
  return apiGet<any>('/core/api/get_domain_list');
};

/**
 * 用户登录
 */
export const authLogin = (params: {
  username: string;
  password: string;
  domain: string;
  binding_id?: number;
}) => {
  return apiPost<any>('/core/api/login/', params);
};

export const verifyOtpLogin = (params: { challenge_id: string; otp_code: string }) => {
  return apiPost<LoginResultResponse<ExternalLoginResult>>('/core/api/verify_otp_login/', params);
};

export const resetPassword = (token: string, password: string) => {
  return apiPost<LoginResultResponse<{ token?: string }>>('/core/api/reset_pwd/', { password }, {
    headers: { Authorization: `Bearer ${token}` },
  });
};

/**
 * 获取登录信息
 */
export const getLoginInfo = () => {
  return apiGet<any>('/core/api/login_info');
};

export const authLogout = (token: string) => {
  return apiPost<any>('/core/api/logout/', { token });
};
