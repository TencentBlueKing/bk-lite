'use client';

import React, { useCallback, useMemo } from 'react';
import { Switch, Form, Menu, Button, Alert } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import EntityList from '@/components/entity-list';
import OperateModal from '@/components/operate-modal';
import DynamicForm from '@/components/dynamic-form';
import PermissionWrapper from '@/components/permission';
import { AuthSource } from '@/app/system-manager/types/security';
import wechatAuthImg from '@/app/system-manager/img/wechat_auth.png';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import {
  getNewAuthSourceFormFields,
  getBluekingFormFields,
  getWeChatFormFields,
} from '@/app/system-manager/components/security/authSourceFormConfig';
import { useAuthSourceModal, copyToClipboard } from '@/app/system-manager/hooks/useAuthSourceModal';

interface AuthSourcesListProps {
  authSources: AuthSource[];
  loading: boolean;
  roleTreeData: TreeDataNode[];
  onUpdate: (sources: AuthSource[]) => void;
}

const AuthSourcesList: React.FC<AuthSourcesListProps> = ({
  authSources,
  loading,
  roleTreeData,
  onUpdate,
}) => {
  const { t } = useTranslation();

  const {
    isModalVisible,
    editingSource,
    modalLoading,
    dynamicForm,
    selectedRoles,
    setSelectedRoles,
    handleAddAuthSource,
    handleEditSource,
    handleAuthSourceSubmit,
    handleModalCancel,
    handleAuthSourceToggle,
    handleSyncAuthSource,
    handleSourceTypeChange,
  } = useAuthSourceModal({ authSources, onUpdate, t });

  const handleCopy = useCallback((text: string) => {
    copyToClipboard(text, t);
  }, [t]);

  const menuActions = useCallback((item: AuthSource) => (
    <Menu>
      <Menu.Item key="edit" onClick={() => handleEditSource(item)}>
        <PermissionWrapper requiredPermissions={['Edit']}>
          {t('common.edit')}
        </PermissionWrapper>
      </Menu.Item>
      <Menu.Item key="sync" onClick={() => handleSyncAuthSource(item)}>
        <PermissionWrapper requiredPermissions={['Edit']}>
          {t('system.security.syncNow')}
        </PermissionWrapper>
      </Menu.Item>
    </Menu>
  ), [handleEditSource, handleSyncAuthSource, t]);

  const getAuthImageSrc = useCallback((sourceType: string) => {
    const imageMap: Record<string, string> = {
      wechat: wechatAuthImg.src,
    };
    return imageMap[sourceType] || undefined;
  }, []);

  const operateSection = useMemo(() => (
    <PermissionWrapper requiredPermissions={['Add']}>
      <Button
        type="primary"
        icon={<PlusOutlined />}
        onClick={handleAddAuthSource}
        className="ml-2"
      >
        {t('common.add')}
      </Button>
    </PermissionWrapper>
  ), [handleAddAuthSource, t]);

  const descSlot = useCallback((item: AuthSource) => (
    <div className="flex items-center justify-end">
      <div onClick={(e) => e.stopPropagation()}>
        <Switch
          size="small"
          checked={item.enabled}
          onChange={(checked) => handleAuthSourceToggle(item, checked)}
        />
      </div>
    </div>
  ), [handleAuthSourceToggle]);

  const formFieldsConfig = useMemo(() => ({
    t,
    dynamicForm,
    copyToClipboard: handleCopy,
    roleTreeData,
    selectedRoles,
    setSelectedRoles,
  }), [t, dynamicForm, handleCopy, roleTreeData, selectedRoles, setSelectedRoles]);

  const renderWeChatModal = () => (
    <div className="w-full">
      <Alert type="info" showIcon message={t('system.security.informationTip')} className="mb-4" />
      <div className="flex">
        <div className="flex-1">
          <DynamicForm form={dynamicForm} fields={getWeChatFormFields(formFieldsConfig)} />
        </div>
        <div className="w-64 flex justify-center items-start ml-4">
          {editingSource && getAuthImageSrc(editingSource.source_type) && (
            <img
              src={getAuthImageSrc(editingSource.source_type)}
              alt={`${editingSource.source_type} auth`}
              className="max-w-full h-auto"
              onError={(e) => {
                e.currentTarget.style.display = 'none';
              }}
            />
          )}
        </div>
      </div>
    </div>
  );

  const renderStandardModal = () => (
    <Form
      form={dynamicForm}
      layout="vertical"
      onValuesChange={(changedValues) => {
        if (changedValues.source_type) {
          handleSourceTypeChange(changedValues.source_type);
        }
      }}
    >
      <Form.Item
        noStyle
        shouldUpdate={(prevValues, currentValues) =>
          prevValues.source_type !== currentValues.source_type
        }
      >
        {({ getFieldValue }) => {
          const currentSourceType = getFieldValue('source_type') ||
            (editingSource?.source_type !== 'wechat' ? editingSource?.source_type : 'bk_lite');

          const formFields = currentSourceType === 'bk_login'
            ? getBluekingFormFields({
              ...formFieldsConfig,
              isBuiltIn: editingSource?.is_build_in || false,
            })
            : getNewAuthSourceFormFields({
              ...formFieldsConfig,
              isBuiltIn: editingSource?.is_build_in || false,
            });

          return <DynamicForm form={dynamicForm} fields={formFields} />;
        }}
      </Form.Item>
    </Form>
  );

  return (
    <>
      <EntityList
        data={authSources}
        loading={loading}
        search
        menuActions={menuActions}
        onCardClick={handleEditSource}
        operateSection={operateSection}
        descSlot={descSlot}
      />

      <OperateModal
        title={editingSource ? t('common.edit') : t('common.add')}
        open={isModalVisible}
        onOk={handleAuthSourceSubmit}
        onCancel={handleModalCancel}
        width={editingSource?.source_type === 'wechat' ? 1000 : 800}
        confirmLoading={modalLoading}
        maskClosable={!modalLoading}
      >
        {editingSource?.source_type === 'wechat' ? renderWeChatModal() : renderStandardModal()}
      </OperateModal>
    </>
  );
};

export default AuthSourcesList;
