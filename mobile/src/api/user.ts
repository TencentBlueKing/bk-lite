import { apiGet, apiPost } from './request';

// 获取用户信息
export const getUserInfo = () => {
    return apiGet<any>('/api/proxy/console_mgmt/get_user_info');
};

// 更新用户信息
export const updateUserInfo = (data: any) => {
    return apiPost<any>('/api/proxy/console_mgmt/update_user_base_info/', data);
}