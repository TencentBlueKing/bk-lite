import { apiGet, apiPost } from './request';

export interface AccountOrganization {
  id?: string | number;
  name?: string;
}

export interface AccountRole {
  id?: string | number;
  name: string;
  app?: string | null;
  app_display_name?: string;
}

export interface AccountUserInfo {
  username: string;
  display_name: string;
  email: string;
  domain: string;
  locale: string;
  timezone: string;
  group_list?: AccountOrganization[];
  role_list?: AccountRole[];
}

export interface UpdateUserBaseInfoInput {
  display_name?: string;
  locale?: string;
  timezone?: string;
}

interface ApiResponse<T> {
  result: boolean;
  data: T;
  message?: string;
}

export const getUserInfo = () => apiGet<ApiResponse<AccountUserInfo>>('/console_mgmt/get_user_info');

export const updateUserInfo = (data: UpdateUserBaseInfoInput) => (
  apiPost<ApiResponse<AccountUserInfo>>('/console_mgmt/update_user_base_info/', data)
);
