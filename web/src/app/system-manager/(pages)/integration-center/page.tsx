// Route: /system-manager/integration-center
'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { ReloadOutlined } from '@ant-design/icons';
import { Button, Menu, Modal, message, Tag } from 'antd';

import EntityList from '@/components/entity-list';
import PermissionWrapper from '@/components/permission';
import TopSection from '@/components/top-section';
import { useRouter } from 'next/navigation';
import { useIntegrationCenterApi } from '@/app/system-manager/api/integration-center';
import type { IntegrationInstance, ProviderManifest } from '@/app/system-manager/types/integration-center';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';
import commonStyles from '@/app/system-manager/styles/common.module.scss';

import CreateIntegrationInstanceModal from './CreateIntegrationInstanceModal';
import { buildIntegrationInstanceCardItem, filterIntegrationInstancesByName, getIntegrationCapabilityTagColor, type IntegrationInstanceCardItem } from '@/app/system-manager/utils/intergrationCenter';

const IntegrationCenterPage: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();
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
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          await deleteInstance(instance.id);
          message.success(t('common.delSuccess'));
          await fetchInstances();
        } catch {
          message.error(t('common.delFailed'));
        }
      },
    });
  };

  const getMenuActions = (instance: IntegrationInstance) => (
    <Menu className={commonStyles.batchOperationMenu}>
      <Menu.Item key="edit" onClick={() => setEditingInstance(instance)}>
        <PermissionWrapper requiredPermissions={['Edit']}>
          <Button type="text" className="w-full">
            {t('common.edit')}
          </Button>
        </PermissionWrapper>
      </Menu.Item>
      <Menu.Item key="delete" onClick={() => handleDeleteInstance(instance)}>
        <PermissionWrapper requiredPermissions={['Delete']}>
          <Button type="text" className="w-full">
            {t('common.delete')}
          </Button>
        </PermissionWrapper>
      </Menu.Item>
    </Menu>
  );

  const filteredInstances = useMemo(
    () => filterIntegrationInstancesByName(instances, instanceSearch),
    [instances, instanceSearch],
  );

  const instanceCards = useMemo(
    () => filteredInstances.map((instance) => {
      const provider = providers.find((p) => p.key === instance.provider_key);
      return buildIntegrationInstanceCardItem(instance, provider, t);
    }),
    [filteredInstances, providers, t],
  );

  const generateDescSlot = (data: IntegrationInstanceCardItem) => {
    const capabilityKeyMap: Record<string, string> = {
      user_sync: 'userSync',
      login_auth: 'loginAuth',
      im_notification: 'imNotification',
    };

    const capabilitiesTag = (data.provider?.capabilities || []).map((capability) => {
      const color = getIntegrationCapabilityTagColor(data.raw, capability.key);
      return (
        <Tag
          key={capability.key}
          bordered
          color={color}
          className={`mr-0 rounded-md font-mini ${
            color === 'green'
              ? 'border-[#b7eb8f] bg-[#f6ffed] text-[#389e0d]'
              : 'border-[#d9d9d9] bg-[#fafafa] text-[#8c8c8c]'
          }`}
        >
          <span className="flex items-center gap-1">
            <span className={`h-2 w-2 rounded-full ${color === 'green' ? 'bg-[#389e0d]' : 'bg-[#bfbfbf]'}`} />
            <span>{t(`system.integrationCenter.capability.${capabilityKeyMap[capability.key]}`)}</span>
          </span>
        </Tag>
      );
    });
    return (
      <div className='flex flex-wrap justify-end gap-1'>
        {capabilitiesTag}
      </div>
    )
  }


  const operateSection = (
    <div className="ml-2 flex flex-wrap items-center gap-2">
      <PermissionWrapper requiredPermissions={['Add']}>
        <Button type="primary" onClick={() => setCreateModalOpen(true)}>
          {t('system.integrationCenter.addInstanceButton')}
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
  );

  return (
    <div className="w-full space-y-4">
      <TopSection
        title={t('system.integrationCenter.pageTitle')}
        content={t('system.integrationCenter.pageDesc')}
      />

      <EntityList
        data={instanceCards}
        loading={loadingInstances || loadingProviders}
        onSearch={setInstanceSearch}
        onCardClick={(item: IntegrationInstanceCardItem) => handleInstanceClick(item.raw)}
        menuActions={(item: IntegrationInstanceCardItem) => getMenuActions(item.raw)}
        operateSection={operateSection}
        descSlot={generateDescSlot}
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
