'use client';

import React, { useState, useEffect } from 'react';
import { message, Segmented } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSecurityApi } from '@/app/system-manager/api/security';
import { AuthSource } from '@/app/system-manager/types/security';
import { enhanceAuthSourcesList } from '@/app/system-manager/utils/authSourceUtils';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import { useUserApi } from '@/app/system-manager/api/user/index';
import { useClientData } from '@/context/client';
import LoginSettings from '@/app/system-manager/components/security/authSettings';
import AuthSourcesList from '@/app/system-manager/components/security/sourcesList';
import UserLoginLogs from '@/app/system-manager/components/security/loginLogs';

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
  const { getSystemSettings, updateOtpSettings, getAuthSources } = useSecurityApi();
  const { clientData } = useClientData();
  const { getRoleList } = useUserApi();
  const [roleTreeData, setRoleTreeData] = useState<TreeDataNode[]>([]);

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

  const handleTabChange = (value: string) => {
    setActiveTab(value);
  };

  const tabContent = {
    '1': (
      <LoginSettings
        otpEnabled={pendingOtpEnabled}
        loginExpiredTime={pendingLoginExpiredTime}
        loading={loading}
        onOtpChange={handleOtpChange}
        onLoginExpiredTimeChange={handleLoginExpiredTimeChange}
        onSave={handleSaveSettings}
      />
    ),
    '2': (
      <AuthSourcesList
        authSources={authSources}
        loading={authSourcesLoading}
        roleTreeData={roleTreeData}
        onUpdate={setAuthSources}
      />
    ),
    '3': (
      <UserLoginLogs />
    )
  };

  return (
    <div className="w-full">
      <Segmented
        options={[
          { label: t('system.security.settings'), value: '1' },
          { label: t('system.security.authSources'), value: '2' },
          { label: t('system.security.userLogs'), value: '3' }
        ]}
        value={activeTab}
        onChange={handleTabChange}
        className="mb-4"
      />
      
      {tabContent[activeTab as '1' | '2' | '3']}
    </div>
  );
};

export default SecurityPage;
