'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button,
  Modal,
  message,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';

import PageLayout from '@/components/page-layout';
import TopSection from '@/components/top-section';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
import UserSyncSourceList, {
  type UserSyncSourceCardItem,
  type UserSyncStatusTone,
} from '@/app/system-manager/components/user/user-sync/UserSyncSourceList';
import UserSyncOperateModal from '@/app/system-manager/components/user/user-sync/UserSyncOperateModal';
import UserSyncBasicModal from '@/app/system-manager/components/user/user-sync/UserSyncBasicModal';
import UserSyncConfigModal from '@/app/system-manager/components/user/user-sync/UserSyncConfigModal';
import UserSyncStrategyModal from '@/app/system-manager/components/user/user-sync/UserSyncStrategyModal';
import UserSyncRecordsDrawer from '@/app/system-manager/components/user/user-sync/UserSyncRecordsDrawer';
import { useIntegrationCenterApi } from '@/app/system-manager/api/integration-center';
import type { ProviderManifest } from '@/app/system-manager/types/integration-center';
import { useUserSyncApi } from '@/app/system-manager/api/user-sync';
import type {
  AvailableInstance,
  UserSyncSource,
  UserSyncSourceBasicFormValues,
  UserSyncSourceConfigFormValues,
  UserSyncSourceCreateFormValues,
  UserSyncSourceStrategyFormValues,
} from '@/app/system-manager/types/user-sync';
import {
  buildBasicUpdatePayload,
  buildConfigPreviewPayload,
  buildConfigUpdatePayload,
  buildCreateSyncSourcePayload,
  buildStrategyUpdatePayload,
} from '@/app/system-manager/utils/userSyncUtils';
import {
  type MappingRow,
  type RecordRow,
  RUN_STATUS_TEXT_STYLE,
  toFieldMappingPayload,
} from '@/app/system-manager/utils/userSyncPageUtils';
import { isSilentRequestError } from '@/utils/request';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

interface UserSyncEntityItem extends UserSyncSourceCardItem {
  raw: UserSyncSource;
}

const STATUS_TONE_MAP: Record<keyof typeof RUN_STATUS_TEXT_STYLE, UserSyncStatusTone> = {
  running: 'processing',
  success: 'success',
  failed: 'error',
  partial: 'waiting',
};

const UserSyncPage: React.FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const {
    getSyncSources,
    createSyncSource,
    updateSyncSource,
    deleteSyncSource,
    getAvailableInstances,
    syncNow,
    getPagedRecords,
    previewSyncSource,
  } = useUserSyncApi();
  const { getProviders } = useIntegrationCenterApi();

  const [sources, setSources] = useState<UserSyncSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [availableInstances, setAvailableInstances] = useState<AvailableInstance[]>([]);
  const [providers, setProviders] = useState<ProviderManifest[]>([]);
  const [providersLoading, setProvidersLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [createPreviewLoading, setCreatePreviewLoading] = useState(false);

  const [basicSource, setBasicSource] = useState<UserSyncSource | null>(null);
  const [basicLoading, setBasicLoading] = useState(false);

  const [configSource, setConfigSource] = useState<UserSyncSource | null>(null);
  const [configLoading, setConfigLoading] = useState(false);
  const [configPreviewLoading, setConfigPreviewLoading] = useState(false);

  const [strategySource, setStrategySource] = useState<UserSyncSource | null>(null);
  const [strategyLoading, setStrategyLoading] = useState(false);

  const [recordsOpen, setRecordsOpen] = useState(false);
  const [records, setRecords] = useState<RecordRow[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [recordsPagination, setRecordsPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 10,
  });

  const fetchSources = async () => {
    setLoading(true);
    try {
      const data = await getSyncSources();
      setSources(data);
    } finally {
      setLoading(false);
    }
  };

  const fetchAvailableInstances = async () => {
    setProvidersLoading(true);
    try {
      const [instancesData, providersData] = await Promise.all([
        getAvailableInstances(),
        getProviders(),
      ]);
      setAvailableInstances(instancesData);
      setProviders(providersData);
    } catch {
      // handled by request interceptor
    } finally {
      setProvidersLoading(false);
    }
  };

  useEffect(() => {
    fetchSources();
    fetchAvailableInstances();
  }, []);

  const entityListItems = useMemo<UserSyncEntityItem[]>(() => {
    return sources.map((source) => {
      const providerKey =
        availableInstances.find((item) => item.id === source.integration_instance)?.provider_key || '';
      const latestStatus = source.latest_run?.status;
      const latestSyncTimeText = source.latest_run?.started_at
        ? convertToLocalizedTime(source.latest_run.started_at, 'YYYY-MM-DD HH:mm')
        : '--';
      const latestStatusText = latestStatus
        ? t(`system.user.userSyncPage.runStatus.${latestStatus}`)
        : t('system.user.userSyncPage.noRun');
      const syncCycleText = source.schedule_config?.enabled && source.schedule_config.sync_time
        ? source.schedule_config.sync_time
        : t('system.user.userSyncPage.manualSync');

      return {
        id: source.id,
        raw: source,
        name: source.name,
        description: source.description || '--',
        providerIcon: providerKey || 'shezhi',
        integrationSystemName: source.integration_instance_name || '--',
        rootGroupName: source.root_group_name || '--',
        syncedUsersText: source.latest_run ? source.latest_run.synced_user_count.toLocaleString() : '--',
        syncCycleText,
        latestSyncTimeText,
        latestStatusText,
        latestStatusTone: latestStatus ? STATUS_TONE_MAP[latestStatus] : 'default',
        syncDisabled: !source.enabled,
      };
    });
  }, [availableInstances, convertToLocalizedTime, sources, t]);

  const showPreviewSuccess = (result: { estimated_user_count: number; estimated_group_count?: number }) => {
    const countMessage = result.estimated_group_count !== undefined
      ? t('system.user.userSyncPage.previewSuccessWithGroups')
        .replace('{{userCount}}', String(result.estimated_user_count))
        .replace('{{groupCount}}', String(result.estimated_group_count))
      : t('system.user.userSyncPage.previewSuccess')
        .replace('{{userCount}}', String(result.estimated_user_count));
    message.success(countMessage);
  };

  const openAdd = () => {
    setCreateOpen(true);
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await Promise.all([fetchSources(), fetchAvailableInstances()]);
    } finally {
      setRefreshing(false);
    }
  };

  const closeCreate = () => {
    if (!createLoading && !createPreviewLoading) {
      setCreateOpen(false);
    }
  };

  const handleCreateSubmit = async (values: UserSyncSourceCreateFormValues, mappingRows: MappingRow[]) => {
    const payload = buildCreateSyncSourcePayload(values, toFieldMappingPayload(mappingRows));

    setCreateLoading(true);
    try {
      await createSyncSource(payload);
      message.success(t('common.addSuccess'));
      setCreateOpen(false);
      fetchSources();
    } catch {
      // handled by request interceptor
    } finally {
      setCreateLoading(false);
    }
  };

  const handleCreatePreview = async (
    values: UserSyncSourceCreateFormValues,
    mappingRows: MappingRow[],
    writeOnlyKeys: Set<string>,
  ) => {
    const payload = buildCreateSyncSourcePayload(values, toFieldMappingPayload(mappingRows));
    const businessConfig = { ...((payload.business_config || {}) as Record<string, unknown>) };
    for (const key of writeOnlyKeys) {
      const value = businessConfig[key];
      if (value === undefined || value === null || value === '') {
        delete businessConfig[key];
      }
    }

    setCreatePreviewLoading(true);
    try {
      const result = await previewSyncSource({
        ...payload,
        business_config: businessConfig,
      });
      showPreviewSuccess(result);
    } catch (err) {
      if (!isSilentRequestError(err)) {
        message.error(err instanceof Error ? err.message : t('system.integrationCenter.testStatusFailed'));
      }
    } finally {
      setCreatePreviewLoading(false);
    }
  };

  const openBasic = (source: UserSyncSource) => {
    setBasicSource(source);
  };

  const closeBasic = () => {
    if (!basicLoading) {
      setBasicSource(null);
    }
  };

  const handleBasicSubmit = async (values: UserSyncSourceBasicFormValues) => {
    if (!basicSource) return;
    const payload = buildBasicUpdatePayload(basicSource, values);

    setBasicLoading(true);
    try {
      await updateSyncSource(basicSource.id, payload);
      message.success(t('common.saveSuccess'));
      setBasicSource(null);
      fetchSources();
    } catch {
      // handled by request interceptor
    } finally {
      setBasicLoading(false);
    }
  };

  const openConfig = (source: UserSyncSource) => {
    setConfigSource(source);
  };

  const closeConfig = () => {
    if (!configLoading && !configPreviewLoading) {
      setConfigSource(null);
    }
  };

  const handleConfigSubmit = async (
    values: UserSyncSourceConfigFormValues,
    mappingRows: MappingRow[],
  ) => {
    if (!configSource) return;
    const payload = buildConfigUpdatePayload(
      configSource,
      values.business_config,
      toFieldMappingPayload(mappingRows),
    );

    setConfigLoading(true);
    try {
      await updateSyncSource(configSource.id, payload);
      message.success(t('common.saveSuccess'));
      setConfigSource(null);
      fetchSources();
    } catch {
      // handled by request interceptor
    } finally {
      setConfigLoading(false);
    }
  };

  const handleConfigPreview = async (
    values: UserSyncSourceConfigFormValues,
    mappingRows: any[],
    writeOnlyKeys: Set<string>,
  ) => {
    if (!configSource) return;

    setConfigPreviewLoading(true);
    try {
      const result = await previewSyncSource(
        buildConfigPreviewPayload(
          configSource,
          values.business_config,
          toFieldMappingPayload(mappingRows),
          writeOnlyKeys,
        )
      );
      showPreviewSuccess(result);
    } catch (err) {
      if (!isSilentRequestError(err)) {
        message.error(err instanceof Error ? err.message : t('system.integrationCenter.testStatusFailed'));
      }
    } finally {
      setConfigPreviewLoading(false);
    }
  };

  const openStrategy = (source: UserSyncSource) => {
    setStrategySource(source);
  };

  const closeStrategy = () => {
    if (!strategyLoading) {
      setStrategySource(null);
    }
  };

  const handleStrategySubmit = async (values: UserSyncSourceStrategyFormValues) => {
    if (!strategySource) return;
    const payload = buildStrategyUpdatePayload(strategySource, values);

    setStrategyLoading(true);
    try {
      await updateSyncSource(strategySource.id, payload);
      message.success(t('common.saveSuccess'));
      setStrategySource(null);
      fetchSources();
    } catch {
      // handled by request interceptor
    } finally {
      setStrategyLoading(false);
    }
  };

  const handleDelete = (source: UserSyncSource) => {
    Modal.confirm({
      title: t('system.user.userSyncPage.deleteConfirm'),
      content: t('system.user.userSyncPage.deleteConfirmContent').replace('{{sourceName}}', source.name),
      okType: 'danger',
      onOk: async () => {
        try {
          await deleteSyncSource(source.id);
          message.success(t('common.deleteSuccess'));
          fetchSources();
        } catch (error) {
          if (!isSilentRequestError(error)) {
            message.error(error instanceof Error ? error.message : t('common.deleteFailed'));
          }
        }
      },
    });
  };

  const handleSyncNow = async (source: UserSyncSource) => {
    try {
      await syncNow(source.id);
      message.success(t('system.user.userSyncPage.syncStarted'));
      fetchSources();
    } catch (error) {
      if (!isSilentRequestError(error)) {
        message.error(t('system.user.userSyncPage.syncFailed'));
      }
    }
  };

  const fetchRecords = useCallback(async (current = 1, pageSize = recordsPagination.pageSize) => {
    setRecordsLoading(true);
    try {
      const data = await getPagedRecords({ page: current, page_size: pageSize });
      setRecords(data.items as RecordRow[]);
      setRecordsPagination((prev) => ({
        ...prev,
        current,
        pageSize,
        total: data.count,
      }));
    } catch {
      // handled by request interceptor
    } finally {
      setRecordsLoading(false);
    }
  }, [getPagedRecords, recordsPagination.pageSize]);

  const openRecords = async () => {
    setRecordsOpen(true);
    setRecords([]);
    setRecordsPagination((prev) => ({
      ...prev,
      current: 1,
    }));
    await fetchRecords(1, recordsPagination.pageSize);
  };

  const handleRecordsPageChange = useCallback((current: number, pageSize: number) => {
    const nextPage = pageSize !== recordsPagination.pageSize ? 1 : current;
    fetchRecords(nextPage, pageSize);
  }, [fetchRecords, recordsPagination.pageSize]);

  const operateSection = useMemo(() => (
    <div className="ml-2 flex flex-wrap items-center gap-2">
      <Button onClick={openRecords} disabled={sources.length === 0}>
        {t('system.user.userSyncPage.records')}
      </Button>
      <PermissionWrapper requiredPermissions={['Add']}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>
          {t('system.user.userSyncPage.addSource')}
        </Button>
      </PermissionWrapper>
      <Button
        type="text"
        icon={<ReloadOutlined />}
        onClick={handleRefresh}
        loading={refreshing}
        aria-label={t('common.refresh')}
      />
    </div>
  ), [handleRefresh, openAdd, openRecords, refreshing, sources.length, t]);

  return (
    <>
      <PageLayout
        height="calc(100vh - 240px)"
        topSection={
          <TopSection
            title={t('system.integrationCenter.capability.userSync')}
            content={t('system.user.userSyncPage.pageDesc')}
          />
        }
        rightSection={
          <UserSyncSourceList
            data={entityListItems}
            loading={loading}
            operateSection={operateSection}
            onEdit={(item) => openBasic(item.raw)}
            onConfig={(item) => openConfig(item.raw)}
            onStrategy={(item) => openStrategy(item.raw)}
            onDelete={(item) => handleDelete(item.raw)}
            onSyncNow={(item) => handleSyncNow(item.raw)}
          />
        }
      />

      <UserSyncOperateModal
        open={createOpen}
        loading={createLoading}
        previewLoading={createPreviewLoading}
        availableInstances={availableInstances}
        providers={providers}
        providersLoading={providersLoading}
        t={t}
        onClose={closeCreate}
        onPreview={handleCreatePreview}
        onSubmit={handleCreateSubmit}
      />

      <UserSyncBasicModal
        open={!!basicSource}
        source={basicSource}
        loading={basicLoading}
        availableInstances={availableInstances}
        t={t}
        onClose={closeBasic}
        onSubmit={handleBasicSubmit}
      />

      <UserSyncConfigModal
        open={!!configSource}
        source={configSource}
        loading={configLoading}
        previewLoading={configPreviewLoading}
        availableInstances={availableInstances}
        providers={providers}
        providersLoading={providersLoading}
        t={t}
        onClose={closeConfig}
        onPreview={handleConfigPreview}
        onSubmit={handleConfigSubmit}
      />

      <UserSyncStrategyModal
        open={!!strategySource}
        source={strategySource}
        loading={strategyLoading}
        t={t}
        onClose={closeStrategy}
        onSubmit={handleStrategySubmit}
      />

      <UserSyncRecordsDrawer
        open={recordsOpen}
        loading={recordsLoading}
        records={records}
        pagination={recordsPagination}
        t={t}
        onPageChange={handleRecordsPageChange}
        onClose={() => setRecordsOpen(false)}
      />
    </>
  );
};

export default UserSyncPage;
