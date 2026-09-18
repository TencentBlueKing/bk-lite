import { useCallback, useEffect, useState } from 'react';
import { message } from 'antd';
import Cookies from 'js-cookie';
import { useUserInfoContext } from '@/context/userInfo';
import useBtnPermissions from '@/hooks/usePermissions';
import useApiClient, { HandledRequestError } from '@/utils/request';
import { CURRENT_TEAM_COOKIE } from '@/utils/userTeamPreference';
import { useTranslation } from '@/utils/i18n';
import { useSettingsApi } from '@/app/system-manager/api/settings';
import type {
  OpenApiTokenCreateFormValues,
  OpenApiTokenServiceCatalog,
  OpenApiTokenTab,
  PersonalOpenApiTokenRow,
  SystemOpenApiTokenRow,
} from '@/app/system-manager/components/openapi-tokens/types';
import {
  asList,
  canManageByOperations,
  docsToCatalog,
  findMenuOperations,
  formValuesToWritePayload,
  isDuplicateTokenNameError,
  toPersonalRow,
  toSystemRow,
  type MenuTreeNode,
} from '@/app/system-manager/utils/openapiTokens';

const SYSTEM_SECRET_MENU = 'system_api_secret';

const isForbidden = (error: unknown) => (
  error instanceof HandledRequestError && error.status === 403
);

export const useOpenApiTokensPage = () => {
  const { t } = useTranslation();
  const { get } = useApiClient();
  const { isSuperUser, loading: userLoading } = useUserInfoContext();
  const { hasPermission } = useBtnPermissions();
  const {
    fetchUserApiSecrets,
    createUserApiSecret,
    updateUserApiSecret,
    deleteUserApiSecret,
    fetchSystemApiTokens,
    createSystemApiToken,
    updateSystemApiToken,
    deleteSystemApiToken,
    fetchOpenApiDocs,
  } = useSettingsApi();

  const [currentTeam, setCurrentTeam] = useState<string | null>(
    () => Cookies.get(CURRENT_TEAM_COOKIE) || null,
  );
  const [personalRows, setPersonalRows] = useState<PersonalOpenApiTokenRow[]>([]);
  const [systemRows, setSystemRows] = useState<SystemOpenApiTokenRow[]>([]);
  const [personalLoading, setPersonalLoading] = useState(false);
  const [systemLoading, setSystemLoading] = useState(false);
  const [canViewSystem, setCanViewSystem] = useState(isSuperUser);
  const [canManageSystem, setCanManageSystem] = useState(isSuperUser);
  const [scopeCatalog, setScopeCatalog] = useState<OpenApiTokenServiceCatalog[]>([]);

  const canManagePersonal = hasPermission(['Add']) || hasPermission(['Delete']);

  const loadPersonal = useCallback(async () => {
    setPersonalLoading(true);
    try {
      const data = asList(await fetchUserApiSecrets());
      setPersonalRows(data.map(toPersonalRow));
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setPersonalLoading(false);
    }
  }, [fetchUserApiSecrets, t]);

  const loadSystem = useCallback(async () => {
    setSystemLoading(true);
    try {
      const data = asList(await fetchSystemApiTokens(true));
      setSystemRows(data.map(toSystemRow));
    } catch (error) {
      setSystemRows([]);
      if (!isForbidden(error)) {
        message.error(t('common.fetchFailed'));
      }
    } finally {
      setSystemLoading(false);
    }
  }, [fetchSystemApiTokens, t]);

  const loadSystemAccess = useCallback(async () => {
    try {
      const menus = await get<MenuTreeNode[]>('/core/api/get_user_menus/', {
        params: { name: 'system-manager' },
        suppressErrorNotification: true,
      });
      const operations = findMenuOperations(menus, SYSTEM_SECRET_MENU);
      const viewable = operations.includes('View');
      setCanViewSystem(viewable);
      setCanManageSystem(canManageByOperations(operations));
      if (viewable) {
        await loadSystem();
      } else {
        setSystemRows([]);
      }
    } catch {
      setCanViewSystem(false);
      setCanManageSystem(false);
    }
  }, [get, loadSystem]);

  const loadCatalog = useCallback(async () => {
    try {
      setScopeCatalog(docsToCatalog(await fetchOpenApiDocs()));
    } catch {
      setScopeCatalog([]);
    }
  }, [fetchOpenApiDocs]);

  useEffect(() => {
    const timer = setInterval(() => {
      const nextTeam = Cookies.get(CURRENT_TEAM_COOKIE) || null;
      setCurrentTeam((prev) => (prev === nextTeam ? prev : nextTeam));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    void loadPersonal();
  }, [currentTeam, loadPersonal]);

  useEffect(() => {
    if (isSuperUser) {
      setCanViewSystem(true);
      setCanManageSystem(true);
      void loadSystem();
      return;
    }
    if (userLoading) {
      return;
    }
    void loadSystemAccess();
  }, [isSuperUser, loadSystem, loadSystemAccess, userLoading]);

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  const handleCreate = async (
    kind: OpenApiTokenTab,
    values: OpenApiTokenCreateFormValues,
  ) => {
    const payload = formValuesToWritePayload(values);
    try {
      if (kind === 'system') {
        const created = await createSystemApiToken({
          ...payload,
          system_id: values.systemId || '',
        });
        await loadSystem();
        return created.api_secret;
      }
      const created = await createUserApiSecret(payload);
      await loadPersonal();
      return created.api_secret;
    } catch (error) {
      if (!isDuplicateTokenNameError(error)) {
        message.error(t('common.saveFailed'));
      }
      throw error;
    }
  };

  const handleEdit = async (
    kind: OpenApiTokenTab,
    id: number,
    values: OpenApiTokenCreateFormValues,
  ) => {
    const payload = formValuesToWritePayload(values);
    try {
      if (kind === 'system') {
        await updateSystemApiToken(id, payload);
        await loadSystem();
        return;
      }
      await updateUserApiSecret(id, payload);
      await loadPersonal();
    } catch (error) {
      if (!isDuplicateTokenNameError(error)) {
        message.error(t('common.updateFailed'));
      }
      throw error;
    }
  };

  const handleRevokePersonal = async (id: number) => {
    try {
      await deleteUserApiSecret(id);
      setPersonalRows((prev) => prev.filter((item) => item.id !== id));
      message.success(t('common.delSuccess'));
    } catch {
      message.error(t('common.delFailed'));
    }
  };

  const handleRevokeSystem = async (id: number) => {
    try {
      await deleteSystemApiToken(id);
      setSystemRows((prev) => prev.filter((item) => item.id !== id));
      message.success(t('common.delSuccess'));
    } catch {
      message.error(t('common.delFailed'));
    }
  };

  return {
    canViewSystem,
    canManagePersonal,
    canManageSystem,
    personalRows,
    systemRows,
    personalLoading,
    systemLoading,
    scopeCatalog,
    handleCreate,
    handleEdit,
    handleRevokePersonal,
    handleRevokeSystem,
  };
};
