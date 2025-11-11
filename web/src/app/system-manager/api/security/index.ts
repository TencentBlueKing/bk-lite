import useApiClient from '@/utils/request';
import { SystemSettings } from '@/app/system-manager/types/security';

export const useSecurityApi = () => {
  const { get, post, patch } = useApiClient();

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
  async function updateOtpSettings({ enableOtp, loginExpiredTime }: { enableOtp: string; loginExpiredTime: string }): Promise<any> {
    return await post('/system_mgmt/system_settings/update_sys_set/', {
      enable_otp: enableOtp,
      login_expired_time: loginExpiredTime
    });
  }

  /**
   * Get auth sources
   * @returns Promise with auth sources data
   */
  async function getAuthSources(): Promise<any> {
    return await get('/system_mgmt/login_module/');
  }

  /**
   * Update auth source
   * @param id - Auth source ID
   * @param data - Updated auth source data
   * @returns Promise with updated auth source
   */
  async function updateAuthSource(id: number, data: any): Promise<any> {
    return await patch(`/system_mgmt/login_module/${id}/`, data);
  }

  /**
   * Create auth source
   * @param data - New auth source data
   * @returns Promise with created auth source
   */
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

  /**
   * Sync auth source data
   * @param id - Auth source ID
   * @returns Promise with sync result
   */
  async function syncAuthSource(id: number): Promise<any> {
    return await patch(`/system_mgmt/login_module/${id}/sync_data/`);
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
    start_time?: string;
    end_time?: string;
    page?: number;
    page_size?: number;
  }): Promise<any> {
    return await get('/system_mgmt/operation_log/', { params });
  }

  return {
    getSystemSettings,
    updateOtpSettings,
    getAuthSources,
    updateAuthSource,
    createAuthSource,
    syncAuthSource,
    getUserLoginLogs,
    getOperationLogs
  };
};
