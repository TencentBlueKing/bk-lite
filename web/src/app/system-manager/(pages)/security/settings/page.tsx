'use client';

import React, { useState, useEffect } from 'react';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSecurityApi } from '@/app/system-manager/api/security';
import LoginSettings from '@/app/system-manager/components/security/authSettings';

const SecuritySettingsPage: React.FC = () => {
  const { t } = useTranslation();
  const [otpEnabled, setOtpEnabled] = useState(false);
  const [pendingOtpEnabled, setPendingOtpEnabled] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loginExpiredTime, setLoginExpiredTime] = useState<string>('24');
  const [pendingLoginExpiredTime, setPendingLoginExpiredTime] = useState<string>('24');
  const { getSystemSettings, updateOtpSettings } = useSecurityApi();

  useEffect(() => {
    fetchSystemSettings();
  }, []);

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

  return (
    <LoginSettings
      otpEnabled={pendingOtpEnabled}
      loginExpiredTime={pendingLoginExpiredTime}
      loading={loading}
      onOtpChange={handleOtpChange}
      onLoginExpiredTimeChange={handleLoginExpiredTimeChange}
      onSave={handleSaveSettings}
    />
  );
};

export default SecuritySettingsPage;
