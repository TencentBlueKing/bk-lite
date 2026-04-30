'use client';

import React from 'react';
import { Menu, Button } from 'antd';
import { useTranslation } from '@/utils/i18n';
import EntityList from '@/components/entity-list';
import styles from '@/app/system-manager/styles/common.module.scss';
import PermissionWrapper from '@/components/permission';
import ApplicationFormModal from '@/app/system-manager/components/application/modify-applicaiton';
import { useApplicationPage } from '@/app/system-manager/hooks/useApplicationPage';

const ApplicationPage = () => {
  const { t } = useTranslation();
  const {
    dataList,
    loading,
    refreshing,
    modalVisible,
    isEdit,
    currentItem,
    handleSearch,
    handleCardClick,
    handleAddNew,
    handleEdit,
    handleDelete,
    handleModalClose,
    handleFormSuccess
  } = useApplicationPage();

  const getMenuActions = (item: any) => (
    <Menu className={styles.batchOperationMenu}>
      <Menu.Item key="edit" onClick={() => handleEdit(item)}>
        <PermissionWrapper requiredPermissions={['Edit']}>
          <Button type="text" className="w-full">{t('common.edit')}</Button>
        </PermissionWrapper>
      </Menu.Item>
      {!item.is_build_in && (
        <Menu.Item key="delete" onClick={() => handleDelete(item)}>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Button type="text" className="w-full">{t('common.delete')}</Button>
          </PermissionWrapper>
        </Menu.Item>
      )}
    </Menu>
  );

  const addButton = (
    <PermissionWrapper requiredPermissions={['Add']}>
      <Button type="primary" onClick={handleAddNew} className="ml-2">
        {t('common.add')}
      </Button>
    </PermissionWrapper>
  );

  return (
    <div className="w-full">
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
