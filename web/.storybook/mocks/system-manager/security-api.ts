import { passwordSettings } from '../../../src/stories/system-manager-user-org-modal.fixtures';

const authSources = [
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
  const createAuthSource = async () => ({ success: true });
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

