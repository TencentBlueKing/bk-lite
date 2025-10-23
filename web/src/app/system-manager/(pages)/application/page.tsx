'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { message, Menu, Button, Modal } from 'antd';
import { useTranslation } from '@/utils/i18n';
import EntityList from '@/components/entity-list';
import { useClientData } from '@/context/client';
import { ClientData } from '@/types/index';
import styles from '@/app/system-manager/styles/common.module.scss';
import PermissionWrapper from '@/components/permission';
import ApplicationFormModal from '@/app/system-manager/components/application/modify-applicaiton';
import { useRoleApi } from '@/app/system-manager/api/application';

const ApplicationPage = () => {
  const { t } = useTranslation();
  const { getAll, loading, refresh } = useClientData();
  const { deleteApplication } = useRoleApi();
  const [dataList, setDataList] = useState<ClientData[]>([]);
  const [modalVisible, setModalVisible] = useState(false);
  const [isEdit, setIsEdit] = useState(false);
  const [currentItem, setCurrentItem] = useState<ClientData | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const processClientData = (data: ClientData[]) => {
    return data
      .filter((client: ClientData) => client.name !== 'ops-console')
      .map((item: ClientData) => ({
        ...item,
        icon: item.icon || item.name,
        is_build_in: item.is_build_in
      }));
  };

  const refreshData = async () => {
    try {
      setRefreshing(true);
      const data = await refresh();
      if (data) {
        setDataList(processClientData(data));
      }
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setRefreshing(false);
    }
  };

  const loadItems = async (searchTerm = '') => {
    try {
      setRefreshing(true);
      const data: ClientData[] = await getAll();
      
      const filteredData = data.filter((item: ClientData) => 
        item.name.toLowerCase().includes(searchTerm.toLowerCase())
      );
      
      setDataList(processClientData(filteredData));
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadItems();
  }, []);

  const handleSearch = async (value: string) => {
    await loadItems(value);
  };

  const handleCardClick = (item: any) => {
    if (item.is_build_in) {
      router.push(`/system-manager/application/manage?id=${item.id}&clientId=${item.name}`);
    } else {
      message.warning(t('system.application.builtinAppClickTip'));
    }
  };

  const router = useRouter();

  const handleAddNew = () => {
    setCurrentItem(null);
    setIsEdit(false);
    setModalVisible(true);
  };

  const handleEdit = (item: any) => {
    setCurrentItem(item);
    setIsEdit(true);
    setModalVisible(true);
  };

  const handleDelete = (item: any) => {
    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          await deleteApplication({ id: item?.id });
          message.success(t('common.delSuccess'));
          await refreshData();
        } catch {
          message.error(t('common.delFailed'));
        }
      }
    });
  };

  const handleModalClose = () => {
    setModalVisible(false);
  };

  const handleFormSuccess = async () => {
    setModalVisible(false);
    await refreshData();
  };

  const getMenuActions = (item: any) => {
    return (
      <Menu className={styles.batchOperationMenu}>
        <Menu.Item key="edit" onClick={() => handleEdit(item)}>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="text"
              className="w-full"
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
        </Menu.Item>
        {!item.is_build_in && (
          <Menu.Item key="delete" onClick={() => {
            handleDelete(item);
          }}>
            <PermissionWrapper requiredPermissions={['Delete']}>
              <Button
                type="text"
                className="w-full"
              >
                {t('common.delete')}
              </Button>
            </PermissionWrapper>
          </Menu.Item>
        )}
      </Menu>
    );
  };

  const addButton = (
    <PermissionWrapper requiredPermissions={['Add']}>
      <Button type="primary" onClick={handleAddNew} className="ml-2">
        {t('common.add')}
      </Button>
    </PermissionWrapper>
  );

  return (
    <div className='w-full'>
      <EntityList
        data={dataList}
        loading={loading || refreshing}
        nameField="display_name"
        onSearch={handleSearch}
        onCardClick={handleCardClick}
        menuActions={getMenuActions}
        operateSection={addButton}
      />
      <ApplicationFormModal 
        visible={modalVisible}
        initialData={
          currentItem ? {
            id: Number(currentItem.id),
            name: currentItem.name,
            display_name: currentItem.display_name,
            description: currentItem.description || '',
            url: currentItem.url || '',
            icon: currentItem.icon || null,
            tags: currentItem.tags || [],
            is_build_in: !!currentItem.is_build_in
          } : null
        }
        isEdit={isEdit}
        onClose={handleModalClose}
        onSuccess={handleFormSuccess}
      />
    </div>
  );
};

export default ApplicationPage;
