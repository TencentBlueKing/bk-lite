// Route: /system-manager/integration-center
'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Modal, message } from 'antd';

import PermissionWrapper from '@/components/permission';
import { useScreenAwareRouter } from '@/console-layout';
import { useIntegrationCenterApi } from '@/app/system-manager/api/integration-center';
import type { IntegrationInstance, ProviderManifest } from '@/app/system-manager/types/integration-center';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
import SystemManagerEntityGrid from '@/app/system-manager/components/system-manager-entity-grid';
import TopSection from '@/components/top-section';
import SystemManagerUnifiedCard from '@/app/system-manager/components/system-manager-unified-card';
import { formatRelativeTime, pickEntityTimestamp } from '@/utils/relativeTime';

import CreateIntegrationInstanceModal from './CreateIntegrationInstanceModal';
import ProviderCapabilityTags from './ProviderCapabilityTags';
import {
  filterIntegrationInstancesByName,
  formatIntegrationInstanceDeleteError,
  getIntegrationCapabilityLabel,
  getIntegrationCapabilityTagColor,
  getIntegrationPrimaryStatusMeta,
  toIntegrationCardStatusTone,
} from '@/app/system-manager/utils/integrationCenter';

const IntegrationCenterPage: React.FC = () => {
  const { t } = useTranslation();
  const router = useScreenAwareRouter();
  const { selectedGroup } = useUserInfoContext();
  const { getProviders, getInstances, createInstance, updateInstance, deleteInstance } = useIntegrationCenterApi();

  const [providers, setProviders] = useState<ProviderManifest[]>([]);
  const [instances, setInstances] = useState<IntegrationInstance[]>([]);
  const [loadingProviders, setLoadingProviders] = useState(true);
  const [loadingInstances, setLoadingInstances] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [instanceSearch, setInstanceSearch] = useState('');
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editingInstance, setEditingInstance] = useState<IntegrationInstance | null>(null);
  const [updating, setUpdating] = useState(false);

  const fetchProviders = async () => {
    setLoadingProviders(true);
    try {
      setProviders(await getProviders());
    } finally {
      setLoadingProviders(false);
    }
  };

  const fetchInstances = async () => {
    setLoadingInstances(true);
    try {
      setInstances(await getInstances());
    } finally {
      setLoadingInstances(false);
    }
  };

  useEffect(() => {
    fetchProviders();
    fetchInstances();
  }, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await fetchInstances();
    } finally {
      setRefreshing(false);
    }
  };

  const handleInstanceClick = (item: IntegrationInstance) => {
    router.push(`/system-manager/integration-center/detail?id=${item.id}`);
  };

  const handleCloseCreateModal = () => {
    if (!creating) {
      setCreateModalOpen(false);
    }
  };

  const handleCloseEditModal = () => {
    if (!updating) {
      setEditingInstance(null);
    }
  };

  const handleCreateDraft = async ({
    provider,
    values,
    continueConfigure,
  }: {
    provider: ProviderManifest;
    values: { name: string; description?: string };
    continueConfigure: boolean;
  }) => {
    if (!selectedGroup?.id) {
      message.error(t('common.fetchFailed'));
      return;
    }

    try {
      setCreating(true);
      const instance = await createInstance({
        name: values.name,
        description: values.description || '',
        provider_key: provider.key,
        config: {},
        team: [Number(selectedGroup.id)],
        is_draft: true,
      });

      message.success(t('system.integrationCenter.createSuccess'));

      if (continueConfigure) {
        router.push(`/system-manager/integration-center/detail?id=${instance.id}`);
        return;
      }

      setCreateModalOpen(false);
      await fetchInstances();
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) {
        return;
      }

      message.error(t('system.integrationCenter.createFailed'));
    } finally {
      setCreating(false);
    }
  };

  const handleUpdateBasicInfo = async ({
    provider,
    values,
  }: {
    provider: ProviderManifest;
    values: { name: string; description?: string };
    continueConfigure: boolean;
  }) => {
    if (!editingInstance) {
      return;
    }

    try {
      setUpdating(true);
      await updateInstance(editingInstance.id, {
        name: values.name,
        description: values.description || '',
        provider_key: provider.key,
      });
      message.success(t('common.saveSuccess'));
      setEditingInstance(null);
      await fetchInstances();
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setUpdating(false);
    }
  };

  const handleDeleteInstance = (instance: IntegrationInstance) => {
    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('system.integrationCenter.deleteConfirmContent'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          await deleteInstance(instance.id);
          message.success(t('common.delSuccess'));
          await fetchInstances();
        } catch (error) {
          message.error(formatIntegrationInstanceDeleteError(error, t, t('common.delFailed')));
        }
      },
    });
  };

  const filteredInstances = useMemo(
    () => filterIntegrationInstancesByName(instances, instanceSearch),
    [instances, instanceSearch],
  );

  const operateSection = (
    <>
      <Button
        icon={<ReloadOutlined />}
        onClick={handleRefresh}
        loading={refreshing}
      >
        {t('common.refresh')}
      </Button>
      <PermissionWrapper requiredPermissions={['Add']}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
          {t('common.new')}
        </Button>
      </PermissionWrapper>
    </>
  );

  return (
    <div className="w-full">
      <TopSection
        className="mb-4"
        title={t('system.integrationCenter.pageTitle')}
        content={t('system.integrationCenter.pageDesc')}
      />
      <SystemManagerEntityGrid
        items={filteredInstances}
        loading={loadingInstances || loadingProviders}
        onSearch={setInstanceSearch}
        actions={operateSection}
        getItemKey={(item) => item.id}
        renderCard={(instance) => {
          const provider = providers.find((item) => item.key === instance.provider_key);
          const statusMeta = getIntegrationPrimaryStatusMeta(instance.status, instance.capability_status);
          const menuItems: MoreActionsDropdownItem[] = [
            {
              key: 'edit',
              label: t('common.edit'),
              permission: 'Edit',
              onClick: () => setEditingInstance(instance),
            },
            {
              key: 'delete',
              label: t('common.delete'),
              permission: 'Delete',
              danger: true,
              onClick: () => handleDeleteInstance(instance),
            },
          ];
          return (
            <SystemManagerUnifiedCard
              name={instance.name}
              description={provider?.name || instance.provider_key}
              icon={instance.provider_key}
              statusTone={toIntegrationCardStatusTone(statusMeta)}
              statusLabel={t(`system.integrationCenter.primaryStatus.${statusMeta.key}`)}
              updatedAt={formatRelativeTime(pickEntityTimestamp(instance), t)}
              menuItems={menuItems}
              onClick={() => handleInstanceClick(instance)}
              body={(
                <ProviderCapabilityTags
                  tags={(provider?.capabilities || []).map((capability) => ({
                    key: capability.key,
                    label: getIntegrationCapabilityLabel(capability.key, t),
                    appearance: getIntegrationCapabilityTagColor(instance, capability.key) === 'green'
                      ? 'ready'
                      : 'inactive',
                  }))}
                />
              )}
            />
          );
        }}
      />

      <CreateIntegrationInstanceModal
        open={createModalOpen}
        providers={providers}
        providersLoading={loadingProviders}
        creating={creating}
        t={t}
        onClose={handleCloseCreateModal}
        onSubmit={handleCreateDraft}
      />

      <CreateIntegrationInstanceModal
        open={Boolean(editingInstance)}
        mode="edit"
        providers={providers}
        providersLoading={loadingProviders}
        creating={updating}
        initialProvider={providers.find((item) => item.key === editingInstance?.provider_key) || null}
        initialValues={editingInstance ? {
          name: editingInstance.name,
          description: editingInstance.description || '',
        } : null}
        t={t}
        onClose={handleCloseEditModal}
        onSubmit={handleUpdateBasicInfo}
      />
    </div>
  );
};

export default IntegrationCenterPage;
