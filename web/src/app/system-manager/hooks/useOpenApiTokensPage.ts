import { useCallback, useEffect, useState } from 'react';
import { message } from 'antd';
import Cookies from 'js-cookie';
import { HandledRequestError } from '@/utils/request';
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
  docsToCatalog,
  formValuesToWritePayload,
  isDuplicateTokenNameError,
  toPersonalRow,
  toSystemRow,
} from '@/app/system-manager/utils/openapiTokens';

const isForbidden = (error: unknown) => (
  error instanceof HandledRequestError && error.status === 403
);

export const useOpenApiTokensPage = () => {
  const { t } = useTranslation();
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
  const [scopeCatalog, setScopeCatalog] = useState<OpenApiTokenServiceCatalog[]>([]);

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
    void Promise.all([loadPersonal(), loadSystem()]);
  }, [currentTeam, loadPersonal, loadSystem]);

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
