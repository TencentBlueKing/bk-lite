'use client';

import React from 'react';
import { Button } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
import ApplicationFormModal from '@/app/system-manager/components/application/modify-applicaiton';
import { useApplicationPage } from '@/app/system-manager/hooks/useApplicationPage';
import SystemManagerEntityGrid from '@/app/system-manager/components/system-manager-entity-grid';
import SystemManagerUnifiedCard from '@/app/system-manager/components/system-manager-unified-card';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';

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

  const addButton = (
    <PermissionWrapper requiredPermissions={['Add']}>
      <Button type="primary" icon={<PlusOutlined />} onClick={handleAddNew}>
        {t('common.new')}
      </Button>
    </PermissionWrapper>
  );

  return (
    <div className="w-full">
      <SystemManagerEntityGrid
        title={t('system.application.pageTitle')}
        description={t('system.application.pageDesc')}
        items={dataList}
        loading={loading || refreshing}
        onSearch={handleSearch}
        getSearchText={(item) => item.display_name || item.name || ''}
        actions={addButton}
        getItemKey={(item) => item.id}
        renderCard={(item) => {
          const menuItems: MoreActionsDropdownItem[] = [
            {
              key: 'edit',
              label: t('common.edit'),
              permission: 'Edit',
              onClick: () => handleEdit(item),
            },
            ...(!item.is_build_in ? [{
              key: 'delete',
              label: t('common.delete'),
              permission: 'Delete',
              danger: true,
              onClick: () => handleDelete(item),
            } satisfies MoreActionsDropdownItem] : []),
          ];
          return (
            <SystemManagerUnifiedCard
              name={item.display_name || item.name}
              description={item.description}
              icon={item.icon || item.name}
              origin={item.is_build_in ? 'builtin' : 'external'}
              menuItems={menuItems}
              onClick={() => handleCardClick(item)}
            />
          );
        }}
      />
      <ApplicationFormModal
        visible={modalVisible}
        initialData={
          currentItem ? {
            id: Number(currentItem.id),
            name: currentItem.name,
            display_name: currentItem.source_display_name || currentItem.display_name,
            description: currentItem.source_description || currentItem.description || '',
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
