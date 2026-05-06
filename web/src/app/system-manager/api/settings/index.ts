import { useCallback } from 'react';
import useApiClient from '@/utils/request';

export interface UserApiSecretListItem {
  id: number;
  username: string;
  domain: string;
  team: number;
  team_name?: string;
  created_at: string;
  updated_at: string;
  api_secret_preview: string;
}

export interface UserApiSecretCreateResponse {
  id: number;
  username: string;
  domain: string;
  team: number;
  team_name?: string;
  created_at: string;
  updated_at: string;
  api_secret: string;
}

export const useSettingsApi = () => {
  const { get, post, del } = useApiClient();

  const getPortalSettings = useCallback(async (): Promise<{
    portal_name?: string;
    portal_logo_url?: string;
    portal_favicon_url?: string;
    watermark_enabled?: string;
    watermark_text?: string;
  }> => {
    return get('/system_mgmt/system_settings/get_sys_set/');
  }, [get]);

  const updatePortalSettings = useCallback(async (params: {
    portal_name?: string;
    portal_logo_url?: string;
    portal_favicon_url?: string;
    watermark_enabled?: string;
    watermark_text?: string;
  }): Promise<void> => {
    await post('/system_mgmt/system_settings/update_sys_set/', params);
  }, [post]);

  /**
   * Fetches user API secrets.
   */
  const fetchUserApiSecrets = useCallback(async (): Promise<UserApiSecretListItem[]> => {
    return get('/base/user_api_secret/');
  }, [get]);

  /**
   * Fetches teams/groups.
   */
  const fetchTeams = useCallback(async (): Promise<any[]> => {
    return get('/system_mgmt/group/get_teams/');
  }, [get]);

  /**
   * Deletes a user API secret by ID.
   * @param id - Secret ID.
   */
  const deleteUserApiSecret = useCallback(async (id: number): Promise<void> => {
    await del(`/base/user_api_secret/${id}/`);
  }, [del]);

  /**
   * Creates a new user API secret.
   */
  const createUserApiSecret = useCallback(async (): Promise<UserApiSecretCreateResponse> => {
    return post('/base/user_api_secret/');
  }, [post]);

  return {
    getPortalSettings,
    updatePortalSettings,
    fetchUserApiSecrets,
    fetchTeams,
    deleteUserApiSecret,
    createUserApiSecret,
  };
};
