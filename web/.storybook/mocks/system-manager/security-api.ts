import type { AuthSource } from '../../../src/app/system-manager/types/security';
import { passwordSettings } from '../../../src/stories/system-manager-user-org-modal.fixtures';

interface CreateAuthSourcePayload {
  name: string;
  source_type: string;
  other_config: {
    namespace?: string;
    root_group?: string;
    domain?: string;
    default_roles?: number[];
    sync?: boolean;
    sync_time?: string;
    bk_url?: string;
    app_token?: string;
    app_id?: string;
    app_secret?: string;
  };
  enabled?: boolean;
}

const authSources: AuthSource[] = [
  {
    id: 1,
    name: 'BlueKing SSO',
    source_type: 'oauth',
    other_config: {
      namespace: 'bk',
      root_group: 'Default',
      domain: 'domain.com',
      default_roles: [1001],
      sync: true,
      sync_time: '02:00',
    },
    enabled: true,
    is_build_in: true,
  },
];

const buildAuthSource = (id: number, data: CreateAuthSourcePayload): AuthSource => ({
  id,
  name: data.name,
  source_type: data.source_type,
  app_id: data.other_config?.app_id,
  app_secret: data.other_config?.app_secret,
  other_config: {
    namespace: data.other_config?.namespace,
    root_group: data.other_config?.root_group,
    domain: data.other_config?.domain,
    default_roles: data.other_config?.default_roles || [],
    sync: data.other_config?.sync ?? false,
    sync_time: data.other_config?.sync_time || '02:00',
    bk_url: data.other_config?.bk_url,
    app_token: data.other_config?.app_token,
    app_id: data.other_config?.app_id,
  },
  enabled: data.enabled ?? true,
  is_build_in: false,
});

const loginLogs = [
  {
    id: 1,
    username: 'alice',
    login_time: '2026-06-03 09:00:00',
    location: 'Shanghai',
    os_info: 'macOS',
    browser_info: 'Chrome',
    source_ip: '127.0.0.1',
    status: 'success',
    status_display: 'Success',
  },
];

const operationLogs = [
  {
    id: 1,
    username: 'alice',
    source_ip: '127.0.0.1',
    app: 'monitor',
    action_type: 'update',
    action_type_display: 'Update',
    summary: 'Updated dashboard permissions',
    domain: 'domain.com',
    operation_time: '2026-06-03 09:15:00',
    created_at: '2026-06-03 09:15:00',
  },
];

const errorLogs = [
  {
    id: 1,
    username: 'alice',
    app: 'monitor',
    module: 'permission',
    error_message: 'Permission rule validation failed',
    domain: 'domain.com',
    created_at: '2026-06-03 09:20:00',
  },
];

export const useSecurityApi = () => {
  const getSystemSettings = async () => passwordSettings;

  const updateOtpSettings = async () => ({ success: true });
  const getAuthSources = async () => authSources;
  const updateAuthSource = async () => ({ success: true });
  const createAuthSource = async (data: CreateAuthSourcePayload) => buildAuthSource(authSources.length + 1, data);
  const syncAuthSource = async () => ({ success: true });
  const deleteAuthSource = async () => ({ success: true });

  const getUserLoginLogs = async () => ({
    count: loginLogs.length,
    items: loginLogs,
  });

  const getOperationLogs = async () => ({
    count: operationLogs.length,
    items: operationLogs,
  });

  const getErrorLogs = async () => ({
    count: errorLogs.length,
    items: errorLogs,
  });

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
    getErrorLogs,
  };
};
