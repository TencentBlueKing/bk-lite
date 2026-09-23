import { useCallback } from 'react';
import useApiClient from '@/utils/request';

export interface OpenApiTokenScope {
  mode: 'all' | 'allowlist';
  endpoints?: string[];
}

export interface UserApiSecretListItem {
  id: number;
  username: string;
  domain: string;
  team: number;
  team_name?: string;
  name?: string;
  expires_at?: string | null;
  scope?: OpenApiTokenScope | null;
  created_at: string;
  updated_at: string;
  api_secret_preview: string;
}

export interface UserApiSecretWritePayload {
  name?: string;
  expires_at?: string | null;
  scope?: OpenApiTokenScope | null;
}

export interface UserApiSecretCreateResponse {
  id: number;
  username: string;
  domain: string;
  team: number;
  team_name?: string;
  name?: string;
  expires_at?: string | null;
  scope?: OpenApiTokenScope | null;
  created_at: string;
  updated_at: string;
  api_secret: string;
}

export interface SystemApiTokenListItem {
  id: number;
  system_id: string;
  name?: string;
  expires_at?: string | null;
  scope?: OpenApiTokenScope | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  created_by?: string;
  api_secret_preview: string;
}

export interface SystemApiTokenWritePayload {
  name?: string;
  expires_at?: string | null;
  scope?: OpenApiTokenScope | null;
  enabled?: boolean;
}

export interface SystemApiTokenCreatePayload extends SystemApiTokenWritePayload {
  system_id: string;
}

export interface SystemApiTokenCreateResponse extends SystemApiTokenListItem {
  api_secret: string;
}

export interface NetworkWhiteListItem {
  id: number;
  network: string;
  domain_name: string;
  is_build_in: boolean;
  remark: string;
  enabled: boolean;
  created_at: string;
  created_by?: string;
}

export interface NetworkWhiteListPage {
  count: number;
  items: NetworkWhiteListItem[];
}

export interface OpenAPIFieldSpec {
  type: string;
  required: boolean;
  default?: unknown;
  choices?: unknown;
  min_value?: number;
  max_value?: number;
}

export interface OpenAPIInternalEndpoint {
  path: string;
  method: string;
  summary: string;
  inject: string | null;
  permission: string;
  request_schema: Record<string, OpenAPIFieldSpec>;
}

export interface OpenAPIService {
  name: string;
  kind: 'internal' | 'external';
  endpoints?: OpenAPIInternalEndpoint[];
  doc_url?: string;
}

export interface OpenAPIDocsCatalog {
  services: OpenAPIService[];
}

export const useSettingsApi = () => {
  const { get, post, del, patch } = useApiClient();

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
  const createUserApiSecret = useCallback(
    async (data?: UserApiSecretWritePayload): Promise<UserApiSecretCreateResponse> => {
      return post('/base/user_api_secret/', data ?? {}, { suppressErrorNotification: true });
    },
    [post]
  );

  const updateUserApiSecret = useCallback(
    async (id: number, data: UserApiSecretWritePayload): Promise<UserApiSecretListItem> => {
      return patch(`/base/user_api_secret/${id}/`, data, { suppressErrorNotification: true });
    },
    [patch]
  );

  const fetchNetworkWhiteList = useCallback(async (page: number, pageSize: number): Promise<NetworkWhiteListPage> => {
    return get('/system_mgmt/network_white_list/', { params: { page, page_size: pageSize } });
  }, [get]);

  const createNetworkWhiteList = useCallback(
    async (data: { network?: string; domain_name?: string; remark?: string; enabled?: boolean }): Promise<NetworkWhiteListItem> => {
      return post('/system_mgmt/network_white_list/', data);
    },
    [post]
  );

  const updateNetworkWhiteList = useCallback(
    async (id: number, data: { network?: string; domain_name?: string; remark?: string; enabled?: boolean }): Promise<NetworkWhiteListItem> => {
      return patch(`/system_mgmt/network_white_list/${id}/`, data);
    },
    [patch]
  );

  const deleteNetworkWhiteList = useCallback(async (id: number): Promise<void> => {
    await del(`/system_mgmt/network_white_list/${id}/`);
  }, [del]);

  const fetchOpenApiDocs = useCallback(async (): Promise<OpenAPIDocsCatalog> => {
    return get('/system_mgmt/openapi_docs/');
  }, [get]);

  const fetchSystemApiTokens = useCallback(async (silent = false): Promise<SystemApiTokenListItem[]> => {
    return get('/system_mgmt/system_api_token/', silent ? { suppressErrorNotification: true } : undefined);
  }, [get]);

  const createSystemApiToken = useCallback(
    async (data: SystemApiTokenCreatePayload): Promise<SystemApiTokenCreateResponse> => {
      return post('/system_mgmt/system_api_token/', data, { suppressErrorNotification: true });
    },
    [post]
  );

  const updateSystemApiToken = useCallback(
    async (id: number, data: SystemApiTokenWritePayload): Promise<SystemApiTokenListItem> => {
      return patch(`/system_mgmt/system_api_token/${id}/`, data, { suppressErrorNotification: true });
    },
    [patch]
  );

  const deleteSystemApiToken = useCallback(async (id: number): Promise<void> => {
    await del(`/system_mgmt/system_api_token/${id}/`);
  }, [del]);

  return {
    getPortalSettings,
    updatePortalSettings,
    fetchUserApiSecrets,
    fetchTeams,
    deleteUserApiSecret,
    createUserApiSecret,
    updateUserApiSecret,
    fetchNetworkWhiteList,
    createNetworkWhiteList,
    updateNetworkWhiteList,
    deleteNetworkWhiteList,
    fetchOpenApiDocs,
    fetchSystemApiTokens,
    createSystemApiToken,
    updateSystemApiToken,
    deleteSystemApiToken,
  };
};
