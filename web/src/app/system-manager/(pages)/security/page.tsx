'use client';

import React, { useState, useEffect } from 'react';
import { Switch, message, Form, Segmented, Menu, InputNumber, Button, Alert } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import EntityList from '@/components/entity-list';
import OperateModal from '@/components/operate-modal';
import DynamicForm from '@/components/dynamic-form';
import { useSecurityApi } from '@/app/system-manager/api/security';
import { AuthSource } from '@/app/system-manager/types/security';
import PermissionWrapper from '@/components/permission';
import { enhanceAuthSourcesList } from '@/app/system-manager/utils/authSourceUtils';
import wechatAuthImg from '@/app/system-manager/img/wechat_auth.png';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import { useUserApi } from '@/app/system-manager/api/user/index';
import { useClientData } from '@/context/client';
import { getNewAuthSourceFormFields, getBluekingFormFields, getWeChatFormFields } from '@/app/system-manager/components/security/authSourceFormConfig';

const SecurityPage: React.FC = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('1');
  const [otpEnabled, setOtpEnabled] = useState(false);
  const [pendingOtpEnabled, setPendingOtpEnabled] = useState(false);
  const [loading, setLoading] = useState(false);
  const [authSourcesLoading, setAuthSourcesLoading] = useState(false);
  const [loginExpiredTime, setLoginExpiredTime] = useState<string>('24');
  const [pendingLoginExpiredTime, setPendingLoginExpiredTime] = useState<string>('24');
  const [authSources, setAuthSources] = useState<AuthSource[]>([]);
  const [authSourcesLoaded, setAuthSourcesLoaded] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [editingSource, setEditingSource] = useState<AuthSource | null>(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [dynamicForm] = Form.useForm();
  const { getSystemSettings, updateOtpSettings, getAuthSources, updateAuthSource, createAuthSource, syncAuthSource } = useSecurityApi();
  const { clientData } = useClientData();
  const { getRoleList } = useUserApi();
  const [roleTreeData, setRoleTreeData] = useState<TreeDataNode[]>([]);
  const [selectedRoles, setSelectedRoles] = useState<number[]>([]);

  useEffect(() => {
    fetchSystemSettings();
    fetchRoleInfo();
  }, []);

  useEffect(() => {
    if (activeTab === '2' && !authSourcesLoaded) {
      fetchAuthSources();
    }
  }, [activeTab, authSourcesLoaded]);

  const fetchSystemSettings = async () => {
    try {
      setLoading(true);
      const settings = await getSystemSettings();
      const otpValue = settings.enable_otp === '1';
      setOtpEnabled(otpValue);
      setPendingOtpEnabled(otpValue);
      const expiredTime = settings.login_expired_time || '24';
      setLoginExpiredTime(expiredTime);
      setPendingLoginExpiredTime(expiredTime);
    } catch (error) {
      console.error('Failed to fetch system settings:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchAuthSources = async () => {
    try {
      setAuthSourcesLoading(true);
      const data = await getAuthSources();
      const enhancedData = enhanceAuthSourcesList(data || []);
      setAuthSources(enhancedData);
      setAuthSourcesLoaded(true);
    } catch (error) {
      console.error('Failed to fetch auth sources:', error);
      setAuthSources([]);
      setAuthSourcesLoaded(true);
    } finally {
      setAuthSourcesLoading(false);
    }
  };

  const fetchRoleInfo = async () => {
    try {
      const roleData = await getRoleList({ client_list: clientData });
      setRoleTreeData(
        roleData.map((item: any) => ({
          key: item.id,
          title: item.name,
          selectable: false,
          children: item.children.map((child: any) => ({
            key: child.id,
            title: child.name,
            selectable: true,
          })),
        }))
      );
    } catch {
      message.error(t('common.fetchFailed'));
    }
  };

  const handleOtpChange = (checked: boolean) => {
    setPendingOtpEnabled(checked);
  };

  const handleLoginExpiredTimeChange = (value: string) => {
    setPendingLoginExpiredTime(value);
  };

  const handleSaveSettings = async () => {
    try {
      setLoading(true);
      await updateOtpSettings({ 
        enableOtp: pendingOtpEnabled ? '1' : '0', 
        loginExpiredTime: pendingLoginExpiredTime 
      });
      setOtpEnabled(pendingOtpEnabled);
      setLoginExpiredTime(pendingLoginExpiredTime);
      message.success(t('common.updateSuccess'));
    } catch (error) {
      console.error('Failed to update settings:', error);
      setPendingOtpEnabled(otpEnabled);
      setPendingLoginExpiredTime(loginExpiredTime);
    } finally {
      setLoading(false);
    }
  };

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
            other_config: {
              callback_url: values.callback_url || editingSource.other_config.callback_url,
              redirect_uri: values.redirect_uri
            },
            enabled: values.enabled
          };
        } else if (editingSource.source_type === 'bk_login') {
          updateData = {
            name: values.name,
            source_type: values.source_type,
            other_config: {
              app_id: values.app_id,
              app_token: values.app_token,
              bk_url: values.bk_url,
              namespace: values.namespace,
              root_group: values.root_group,
              default_roles: values.default_roles || selectedRoles,
              sync: values.sync || false,
              sync_time: values.sync_time || "00:00"
            },
            enabled: values.enabled
          };
        } else {
          updateData = {
            name: values.name,
            source_type: values.source_type,
            other_config: {
              namespace: values.namespace,
              root_group: values.root_group,
              domain: values.domain,
              default_roles: values.default_roles || selectedRoles,
              sync: values.sync || false,
              sync_time: values.sync_time || "00:00"
            },
            enabled: values.enabled
          };
        }
        
        await updateAuthSource(editingSource.id, updateData);
        
        const updatedSource = { ...editingSource, ...updateData };
        const enhancedSource = enhanceAuthSourcesList([updatedSource])[0];
        
        setAuthSources(authSources.map(item => 
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
            other_config: {
              app_id: values.app_id,
              app_token: values.app_token,
              bk_url: values.bk_url,
              namespace: values.namespace,
              root_group: values.root_group,
              default_roles: values.default_roles,
              sync: values.sync || false,
              sync_time: values.sync_time || "00:00"
            },
            enabled: values.enabled || true
          };
        } else {
          createData = {
            name: values.name,
            source_type: values.source_type,
            other_config: {
              namespace: values.namespace,
              root_group: values.root_group,
              domain: values.domain,
              default_roles: values.default_roles,
              sync: values.sync || false,
              sync_time: values.sync_time || "00:00"
            },
            enabled: values.enabled || true
          };
        }
        
        const newSource = await createAuthSource(createData);
        const enhancedSource = enhanceAuthSourcesList([newSource])[0];
        
        setAuthSources([...authSources, enhancedSource]);
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
      setAuthSources(authSources.map(item => 
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
        // Fallback: use traditional document.execCommand
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

  const handleTabChange = (value: string) => {
    setActiveTab(value);
  };

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

  const tabContent = {
    '1': (
      <div className="bg-[var(--color-bg)] p-4 rounded-lg shadow-sm mb-4">
        <h3 className="text-base font-semibold mb-4">{t('system.security.loginSettings')}</h3>
        <div className="flex items-center mb-4">
          <span className="text-xs mr-4">{t('system.security.otpSetting')}</span>
          <Switch 
            size="small" 
            checked={pendingOtpEnabled} 
            onChange={handleOtpChange}
            loading={loading}
          />
        </div>
        <div className="flex items-center mb-4">
          <span className="text-xs mr-4">{t('system.security.loginExpiredTime')}</span>
          <InputNumber
            min="1"
            value={pendingLoginExpiredTime}
            onChange={(value) => handleLoginExpiredTimeChange(value?.toString() || '24')}
            disabled={loading}
            addonAfter={t('system.security.hours')}
            style={{ width: '180px' }}                           
          />
        </div>
        <div className="mt-6">
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button 
              type="primary" 
              onClick={handleSaveSettings}
              loading={loading}
            >
              {t('common.save')}
            </Button>
          </PermissionWrapper>
        </div>
      </div>
    ),
    '2': (
      <EntityList
        data={authSources}
        loading={authSourcesLoading}
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
    )
  };

  return (
    <div className="w-full">
      <Segmented
        options={[
          { label: t('system.security.settings'), value: '1' },
          { label: t('system.security.authSources'), value: '2' }
        ]}
        value={activeTab}
        onChange={handleTabChange}
        className="mb-4"
      />
      
      {tabContent[activeTab as '1' | '2']}

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
              // 监听类型变化并更新currentSourceType
              if (changedValues.source_type) {
                // 根据不同类型清空对应的特有字段
                if (changedValues.source_type === 'bk_login') {
                  // 蓝鲸认证源：清空bk_lite特有的字段
                  const fieldsToReset = ['namespace', 'domain', 'sync', 'sync_time'];
                  const resetValues = fieldsToReset.reduce((acc, field) => {
                    acc[field] = undefined;
                    return acc;
                  }, {} as any);
                  dynamicForm.setFieldsValue(resetValues);
                } else {
                  // BK-Lite认证源：清空blueking特有的字段
                  const fieldsToReset = ['app_id', 'app_token', 'bk_url'];
                  const resetValues = fieldsToReset.reduce((acc, field) => {
                    acc[field] = undefined;
                    return acc;
                  }, {} as any);
                  dynamicForm.setFieldsValue(resetValues);
                }
                // 公共字段重置
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
    </div>
  );
};

export default SecurityPage;
