'use client';

import React, { useState } from 'react';
import { Switch, message, Form, Menu, Button, Alert } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import EntityList from '@/components/entity-list';
import OperateModal from '@/components/operate-modal';
import DynamicForm from '@/components/dynamic-form';
import PermissionWrapper from '@/components/permission';
import { AuthSource } from '@/app/system-manager/types/security';
import { enhanceAuthSourcesList } from '@/app/system-manager/utils/authSourceUtils';
import wechatAuthImg from '@/app/system-manager/img/wechat_auth.png';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import { getNewAuthSourceFormFields, getBluekingFormFields, getWeChatFormFields } from '@/app/system-manager/components/security/authSourceFormConfig';
import { useSecurityApi } from '@/app/system-manager/api/security';

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
  onUpdate
}) => {
  const { t } = useTranslation();
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [editingSource, setEditingSource] = useState<AuthSource | null>(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [dynamicForm] = Form.useForm();
  const [selectedRoles, setSelectedRoles] = useState<number[]>([]);
  const { updateAuthSource, createAuthSource, syncAuthSource } = useSecurityApi();

  const handleAddAuthSource = () => {
    setEditingSource(null);
    setSelectedRoles([]);
    dynamicForm.resetFields();
    setIsModalVisible(true);
  };

  const handleAuthSourceSubmit = async () => {
    try {
      setModalLoading(true);
      
      if (editingSource) {
        const values = await dynamicForm.validateFields();
        let updateData: any;
        
        if (editingSource.source_type === 'wechat') {
          updateData = {
            name: values.name,
            app_id: values.app_id,
            app_secret: values.app_secret,
            enabled: values.enabled,
            other_config: {
              redirect_uri: values.redirect_uri,
              callback_url: values.callback_url
            }
          };
        } else if (editingSource.source_type === 'bk_login') {
          updateData = {
            name: values.name,
            source_type: values.source_type,
            enabled: values.enabled,
            other_config: {
              namespace: values.namespace,
              root_group: values.root_group,
              app_id: values.app_id,
              app_token: values.app_token,
              bk_url: values.bk_url,
              default_roles: selectedRoles,
              sync: values.sync,
              sync_time: values.sync_time
            }
          };
        } else {
          updateData = {
            name: values.name,
            source_type: values.source_type,
            enabled: values.enabled,
            other_config: {
              namespace: values.namespace,
              root_group: values.root_group,
              domain: values.domain,
              default_roles: selectedRoles,
              sync: values.sync,
              sync_time: values.sync_time
            }
          };
        }
        
        await updateAuthSource(editingSource.id, updateData);
        
        const updatedSource = { ...editingSource, ...updateData };
        const enhancedSource = enhanceAuthSourcesList([updatedSource])[0];
        
        onUpdate(authSources.map(item => 
          item.id === editingSource.id 
            ? enhancedSource
            : item
        ));
        
        message.success(t('common.updateSuccess'));
      } else {
        const values = await dynamicForm.validateFields();
        let createData: any;
        
        if (values.source_type === 'bk_login') {
          createData = {
            name: values.name,
            source_type: values.source_type,
            enabled: values.enabled,
            other_config: {
              namespace: values.namespace,
              root_group: values.root_group,
              app_id: values.app_id,
              app_token: values.app_token,
              bk_url: values.bk_url,
              default_roles: selectedRoles,
              sync: values.sync,
              sync_time: values.sync_time
            }
          };
        } else {
          createData = {
            name: values.name,
            source_type: values.source_type,
            enabled: values.enabled,
            other_config: {
              namespace: values.namespace,
              root_group: values.root_group,
              domain: values.domain,
              default_roles: selectedRoles,
              sync: values.sync,
              sync_time: values.sync_time
            }
          };
        }
        
        const newSource = await createAuthSource(createData);
        const enhancedSource = enhanceAuthSourcesList([newSource])[0];
        
        onUpdate([...authSources, enhancedSource]);
        message.success(t('common.saveSuccess'));
      }
      
      setIsModalVisible(false);
      setEditingSource(null);
      setSelectedRoles([]);
      dynamicForm.resetFields();
    } catch (error) {
      console.error('Failed to save auth source:', error);
      message.error(editingSource ? t('common.updateFailed') : t('common.createFailed'));
    } finally {
      setModalLoading(false);
    }
  };

  const handleModalCancel = () => {
    if (modalLoading) return;
    setIsModalVisible(false);
    setEditingSource(null);
    dynamicForm.resetFields();
  };

  const handleEditSource = (source: AuthSource) => {
    setEditingSource(source);
    
    if (source.source_type === 'wechat') {
      dynamicForm.setFieldsValue({
        name: source.name,
        app_id: source.app_id,
        app_secret: source.app_secret,
        enabled: source.enabled,
        redirect_uri: source.other_config.redirect_uri,
        callback_url: source.other_config.callback_url
      });
    } else if (source.source_type === 'bk_login') {
      const { other_config } = source;
      const defaultRoles = other_config?.default_roles || [];
      setSelectedRoles(defaultRoles);
      
      dynamicForm.setFieldsValue({
        name: source.name,
        source_type: source.source_type,
        namespace: other_config?.namespace,
        root_group: other_config?.root_group,
        app_id: other_config?.app_id,
        app_token: other_config?.app_token,
        bk_url: other_config?.bk_url,
        sync: other_config?.sync || false,
        sync_time: other_config?.sync_time || '00:00',
        enabled: source.enabled,
        default_roles: defaultRoles
      });
    } else {
      const { other_config } = source;
      const defaultRoles = other_config?.default_roles || [];
      setSelectedRoles(defaultRoles);
      
      dynamicForm.setFieldsValue({
        name: source.name,
        source_type: source.source_type,
        namespace: other_config?.namespace,
        root_group: other_config?.root_group,
        domain: other_config?.domain,
        sync: other_config?.sync || false,
        sync_time: other_config?.sync_time || '00:00',
        enabled: source.enabled,
        default_roles: defaultRoles
      });
    }
    
    setIsModalVisible(true);
  };

  const handleAuthSourceToggle = async (source: AuthSource, enabled: boolean) => {
    try {
      const updateData = { ...source, enabled };
      await updateAuthSource(source.id, updateData);
      onUpdate(authSources.map(item => 
        item.id === source.id 
          ? { ...item, enabled }
          : item
      ));
      
      message.success(t('common.saveSuccess'));
    } catch (error) {
      console.error('Failed to update auth source status:', error);
      message.error(t('common.saveFailed'));
    }
  };

  const handleSyncAuthSource = async (source: AuthSource) => {
    try {
      await syncAuthSource(source.id);
      message.success(t('system.security.syncSuccess'));
    } catch (error) {
      console.error('Failed to sync auth source:', error);
      message.error(t('system.security.syncFailed'));
    }
  };

  const copyToClipboard = (text: string) => {
    try {
      if (navigator?.clipboard?.writeText) {
        navigator.clipboard.writeText(text).then(() => {
          message.success(t('common.copySuccess'));
        }).catch(() => {
          message.error(t('common.copyFailed'));
        });
      } else {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        const successful = document.execCommand('copy');
        document.body.removeChild(textArea);
        
        if (successful) {
          message.success(t('common.copySuccess'));
        } else {
          message.error(t('common.copyFailed'));
        }
      }
    } catch (error) {
      console.error('Copy failed:', error);
      message.error(t('common.copyFailed'));
    }
  };

  const menuActions = (item: AuthSource) => (
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
  );

  const getAuthImageSrc = (sourceType: string) => {
    const imageMap: Record<string, string> = {
      wechat: wechatAuthImg.src,
    };
    return imageMap[sourceType] || undefined;
  };

  const operateSection = (
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
        descSlot={(item: AuthSource) => (
          <div className="flex items-center justify-end">
            <div onClick={(e) => e.stopPropagation()}>
              <Switch
                size="small"
                checked={item.enabled}
                onChange={(checked) => handleAuthSourceToggle(item, checked)}
              />
            </div>
          </div>
        )}
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
        {editingSource?.source_type === 'wechat' && (
          <div className="w-full">
            <Alert type="info" showIcon message={t('system.security.informationTip')} className='mb-4' />
            <div className="flex">
              <div className="flex-1">
                <DynamicForm
                  form={dynamicForm}
                  fields={getWeChatFormFields({
                    t,
                    dynamicForm,
                    copyToClipboard,
                    roleTreeData,
                    selectedRoles,
                    setSelectedRoles
                  })}
                />
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
        )}
        {(!editingSource || editingSource?.source_type !== 'wechat') && (
          <Form
            form={dynamicForm}
            layout="vertical"
            onValuesChange={(changedValues) => {
              if (changedValues.source_type) {
                if (changedValues.source_type === 'bk_login') {
                  const fieldsToReset = ['namespace', 'domain', 'sync', 'sync_time'];
                  const resetValues = fieldsToReset.reduce((acc, field) => {
                    acc[field] = undefined;
                    return acc;
                  }, {} as any);
                  dynamicForm.setFieldsValue(resetValues);
                } else {
                  const fieldsToReset = ['app_id', 'app_token', 'bk_url'];
                  const resetValues = fieldsToReset.reduce((acc, field) => {
                    acc[field] = undefined;
                    return acc;
                  }, {} as any);
                  dynamicForm.setFieldsValue(resetValues);
                }
                dynamicForm.setFieldsValue({ 
                  default_roles: undefined,
                  root_group: undefined
                });
                setSelectedRoles([]);
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
                    t,
                    roleTreeData,
                    selectedRoles,
                    setSelectedRoles,
                    dynamicForm,
                    copyToClipboard,
                    isBuiltIn: editingSource?.is_build_in || false
                  })
                  : getNewAuthSourceFormFields({
                    t,
                    roleTreeData,
                    selectedRoles,
                    setSelectedRoles,
                    dynamicForm,
                    copyToClipboard,
                    isBuiltIn: editingSource?.is_build_in || false
                  });
                return (
                  <DynamicForm
                    form={dynamicForm}
                    fields={formFields}
                  />
                );
              }}
            </Form.Item>
          </Form>
        )}
      </OperateModal>
    </>
  );
};

export default AuthSourcesList;
