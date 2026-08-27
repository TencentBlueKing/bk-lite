import useApiClient from '@/utils/request';
import { SystemSettings } from '@/app/system-manager/types/security';

export const useSecurityApi = () => {
  const { get, post, patch, del } = useApiClient();

  /**
   * Get system settings including OTP status
   * @returns Promise with system settings data
   */
  async function getSystemSettings(): Promise<SystemSettings> {
    return await get('/system_mgmt/system_settings/get_sys_set/');
  }

  /**
   * Update OTP settings
   * @param enableOtp - "1" to enable OTP, "0" to disable
   * @returns Promise with updated settings
   */
  async function updateOtpSettings({
    enableOtp,
    loginExpiredTime,
    pwdSetValidityPeriod,
    pwdSetRequiredCharTypes,
    pwdSetMinLength,
    pwdSetMaxLength,
    pwdSetMaxRetryCount,
    pwdSetLockDuration,
    pwdSetExpiryReminderDays,
    otpWhitelist,
    otpRecommendedApps,
    userCreateInitialPassword,
    userCreateInitialPasswordMode,
    userCreateInitialPasswordEmailChannelId,
  }: {
    enableOtp: string;
    loginExpiredTime: string;
    pwdSetValidityPeriod?: string;
    pwdSetRequiredCharTypes?: string;
    pwdSetMinLength?: string;
    pwdSetMaxLength?: string;
    pwdSetMaxRetryCount?: string;
    pwdSetLockDuration?: string;
    pwdSetExpiryReminderDays?: string;
    otpWhitelist?: string | number[] | string[];
    otpRecommendedApps?: string;
    userCreateInitialPassword?: string;
    userCreateInitialPasswordMode?: 'fixed' | 'random' | 'none' | string;
    userCreateInitialPasswordEmailChannelId?: string | number;
  }): Promise<any> {
    const payload: Record<string, unknown> = {
      enable_otp: enableOtp,
      login_expired_time: loginExpiredTime,
      pwd_set_validity_period: pwdSetValidityPeriod,
      pwd_set_required_char_types: pwdSetRequiredCharTypes,
      pwd_set_min_length: pwdSetMinLength,
      pwd_set_max_length: pwdSetMaxLength,
      pwd_set_max_retry_count: pwdSetMaxRetryCount,
      pwd_set_lock_duration: pwdSetLockDuration,
      pwd_set_expiry_reminder_days: pwdSetExpiryReminderDays,
    };
    if (otpWhitelist !== undefined) {
      payload.otp_whitelist = otpWhitelist;
    }
    if (otpRecommendedApps !== undefined && otpRecommendedApps !== '') {
      payload.otp_recommended_apps = otpRecommendedApps;
    }
    if (userCreateInitialPassword) {
      payload.user_create_initial_password = userCreateInitialPassword;
    }
    if (userCreateInitialPasswordMode) {
      payload.user_create_initial_password_mode = userCreateInitialPasswordMode;
    }
    if (userCreateInitialPasswordEmailChannelId !== undefined && userCreateInitialPasswordEmailChannelId !== '') {
      payload.user_create_initial_password_random_email_channel_id = String(userCreateInitialPasswordEmailChannelId);
    }
    return await post('/system_mgmt/system_settings/update_sys_set/', payload);
  }

  /**
   * @deprecated 认证源菜单与后端 LoginModule 路由已关闭。
   * 后续认证源配置迁移至集成中心 Provider；保留该封装仅供遗留页面代码清理期间参考。
   */
  async function getAuthSources(): Promise<any> {
    return await get('/system_mgmt/login_module/');
  }

  /** @deprecated 同 getAuthSources。 */
  async function updateAuthSource(id: number, data: any): Promise<any> {
    return await patch(`/system_mgmt/login_module/${id}/`, data);
  }

  /** @deprecated 同 getAuthSources。 */
  async function createAuthSource(data: {
    name: string;
    source_type: string;
    other_config: {
      namespace?: string;
      root_group?: string;
      domain?: string;
      default_roles?: number[];
      sync?: boolean;
      sync_time?: string;
    };
    enabled?: boolean;
  }): Promise<any> {
    return await post('/system_mgmt/login_module/', data);
  }

  /** @deprecated 同 getAuthSources；用户同步应使用集成中心 user_sync Provider。 */
  async function syncAuthSource(id: number): Promise<any> {
    return await patch(`/system_mgmt/login_module/${id}/sync_data/`);
  }

  /** @deprecated 同 getAuthSources。 */
  async function deleteAuthSource(id: number): Promise<any> {
    return await del(`/system_mgmt/login_module/${id}/`);
  }

  /**
   * Get user login logs
   * @param params - Query parameters for filtering logs
   * @returns Promise with user login logs data
   */
  async function getUserLoginLogs(params?: {
    status?: 'success' | 'failed';
    username?: string;
    username__icontains?: string;
    source_ip?: string;
    source_ip__icontains?: string;
    domain?: string;
    login_time_start?: string;
    login_time_end?: string;
    page?: number;
    page_size?: number;
  }): Promise<any> {
    return await get('/system_mgmt/user_login_log/', { params });
  }

  /**
   * Get operation logs
   * @param params - Query parameters for filtering logs
   * @returns Promise with operation logs data
   */
  async function getOperationLogs(params?: {
    username?: string;
    app?: string;
    action_type?: string;
    operation_time_start?: string;
    operation_time_end?: string;
    page?: number;
    page_size?: number;
  }): Promise<any> {
    return await get('/system_mgmt/operation_log/', { params });
  }

  /**
   * Get error logs
   * @param params - Query parameters for filtering logs
   * @returns Promise with error logs data
   */
  async function getErrorLogs(params?: {
    time_start?: string;
    time_end?: string;
    username?: string;
    app?: string;
    module?: string;
    page?: number;
    page_size?: number;
  }): Promise<any> {
    return await get('/system_mgmt/error_log/', { params });
  }

  return {
    getSystemSettings,
    updateOtpSettings,
    getAuthSources,
    updateAuthSource,
    createAuthSource,
    syncAuthSource,
    deleteAuthSource,
    getUserLoginLogs,
    getOperationLogs,
    getErrorLogs
  };
};
