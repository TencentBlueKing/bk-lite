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
  const [fetching, setFetching] = useState(false);
  const [loginExpiredTime, setLoginExpiredTime] = useState<string>('24');
  const [pendingLoginExpiredTime, setPendingLoginExpiredTime] = useState<string>('24');
  
  const [passwordExpiration, setPasswordExpiration] = useState<string>('180');
  const [pendingPasswordExpiration, setPendingPasswordExpiration] = useState<string>('180');
  const [passwordComplexity, setPasswordComplexity] = useState<string[]>(['uppercase', 'lowercase', 'digit', 'special']);
  const [pendingPasswordComplexity, setPendingPasswordComplexity] = useState<string[]>(['uppercase', 'lowercase', 'digit', 'special']);
  const [minimumLength, setMinimumLength] = useState<string>('8');
  const [pendingMinimumLength, setPendingMinimumLength] = useState<string>('8');
  const [maximumLength, setMaximumLength] = useState<string>('20');
  const [pendingMaximumLength, setPendingMaximumLength] = useState<string>('20');
  const [loginAttempts, setLoginAttempts] = useState<string>('3');
  const [pendingLoginAttempts, setPendingLoginAttempts] = useState<string>('3');
  const [lockDuration, setLockDuration] = useState<string>('180');
  const [pendingLockDuration, setPendingLockDuration] = useState<string>('180');
  const [reminderDays, setReminderDays] = useState<string>('7');
  const [pendingReminderDays, setPendingReminderDays] = useState<string>('7');
  
  const { getSystemSettings, updateOtpSettings } = useSecurityApi();

  useEffect(() => {
    fetchSystemSettings();
  }, []);

  const fetchSystemSettings = async () => {
    try {
      setFetching(true);
      const settings = await getSystemSettings();
      const otpValue = settings.enable_otp === '1';
      setOtpEnabled(otpValue);
      setPendingOtpEnabled(otpValue);
      const expiredTime = settings.login_expired_time || '24';
      setLoginExpiredTime(expiredTime);
      setPendingLoginExpiredTime(expiredTime);
      
      // 设置密码相关字段
      const pwdExpiration = settings.pwd_set_validity_period || '180';
      setPasswordExpiration(pwdExpiration);
      setPendingPasswordExpiration(pwdExpiration);
      
      const pwdComplexity = settings.pwd_set_required_char_types 
        ? (typeof settings.pwd_set_required_char_types === 'string'
          ? settings.pwd_set_required_char_types.split(',').filter(Boolean)
          : Array.isArray(settings.pwd_set_required_char_types)
            ? settings.pwd_set_required_char_types
            : ['uppercase', 'lowercase', 'digit', 'special'])
        : ['uppercase', 'lowercase', 'digit', 'special'];
      setPasswordComplexity(pwdComplexity);
      setPendingPasswordComplexity(pwdComplexity);
      
      const pwdMinLength = settings.pwd_set_min_length || '8';
      setMinimumLength(pwdMinLength);
      setPendingMinimumLength(pwdMinLength);
      
      const pwdMaxLength = settings.pwd_set_max_length || '20';
      setMaximumLength(pwdMaxLength);
      setPendingMaximumLength(pwdMaxLength);
      
      const pwdRetryCount = settings.pwd_set_max_retry_count || '3';
      setLoginAttempts(pwdRetryCount);
      setPendingLoginAttempts(pwdRetryCount);
      
      const pwdLockDuration = settings.pwd_set_lock_duration || '180';
      setLockDuration(pwdLockDuration);
      setPendingLockDuration(pwdLockDuration);
      
      const pwdReminderDays = settings.pwd_set_expiry_reminder_days || '7';
      setReminderDays(pwdReminderDays);
      setPendingReminderDays(pwdReminderDays);
    } catch (error) {
      console.error('Failed to fetch system settings:', error);
    } finally {
      setFetching(false);
    }
  };

  const handleOtpChange = (checked: boolean) => {
    setPendingOtpEnabled(checked);
  };

  const handleLoginExpiredTimeChange = (value: string) => {
    setPendingLoginExpiredTime(value);
  };

  const handlePasswordExpirationChange = (value: string) => {
    setPendingPasswordExpiration(value);
  };

  const handlePasswordComplexityChange = (value: string[]) => {
    setPendingPasswordComplexity(value);
  };

  const handleMinimumLengthChange = (value: string) => {
    setPendingMinimumLength(value);
  };

  const handleMaximumLengthChange = (value: string) => {
    setPendingMaximumLength(value);
  };

  const handleLoginAttemptsChange = (value: string) => {
    setPendingLoginAttempts(value);
  };

  const handleLockDurationChange = (value: string) => {
    setPendingLockDuration(value);
  };

  const handleReminderDaysChange = (value: string) => {
    setPendingReminderDays(value);
  };

  const handleSaveSettings = async () => {
    try {
      setLoading(true);
      await updateOtpSettings({ 
        enableOtp: pendingOtpEnabled ? '1' : '0', 
        loginExpiredTime: pendingLoginExpiredTime,
        pwdSetValidityPeriod: pendingPasswordExpiration,
        pwdSetRequiredCharTypes: pendingPasswordComplexity.join(','),
        pwdSetMinLength: pendingMinimumLength,
        pwdSetMaxLength: pendingMaximumLength,
        pwdSetMaxRetryCount: pendingLoginAttempts,
        pwdSetLockDuration: pendingLockDuration,
        pwdSetExpiryReminderDays: pendingReminderDays,
      });
      setOtpEnabled(pendingOtpEnabled);
      setLoginExpiredTime(pendingLoginExpiredTime);
      setPasswordExpiration(pendingPasswordExpiration);
      setPasswordComplexity(pendingPasswordComplexity);
      setMinimumLength(pendingMinimumLength);
      setMaximumLength(pendingMaximumLength);
      setLoginAttempts(pendingLoginAttempts);
      setLockDuration(pendingLockDuration);
      setReminderDays(pendingReminderDays);
      message.success(t('common.updateSuccess'));
    } catch (error) {
      console.error('Failed to update settings:', error);
      setPendingOtpEnabled(otpEnabled);
      setPendingLoginExpiredTime(loginExpiredTime);
      setPendingPasswordExpiration(passwordExpiration);
      setPendingPasswordComplexity(passwordComplexity);
      setPendingMinimumLength(minimumLength);
      setPendingMaximumLength(maximumLength);
      setPendingLoginAttempts(loginAttempts);
      setPendingLockDuration(lockDuration);
      setPendingReminderDays(reminderDays);
    } finally {
      setLoading(false);
    }
  };

  return (
    <LoginSettings
      otpEnabled={pendingOtpEnabled}
      loginExpiredTime={pendingLoginExpiredTime}
      passwordExpiration={pendingPasswordExpiration}
      passwordComplexity={pendingPasswordComplexity}
      minimumLength={pendingMinimumLength}
      maximumLength={pendingMaximumLength}
      loginAttempts={pendingLoginAttempts}
      lockDuration={pendingLockDuration}
      reminderDays={pendingReminderDays}
      loading={loading}
      disabled={fetching}
      onOtpChange={handleOtpChange}
      onLoginExpiredTimeChange={handleLoginExpiredTimeChange}
      onPasswordExpirationChange={handlePasswordExpirationChange}
      onPasswordComplexityChange={handlePasswordComplexityChange}
      onMinimumLengthChange={handleMinimumLengthChange}
      onMaximumLengthChange={handleMaximumLengthChange}
      onLoginAttemptsChange={handleLoginAttemptsChange}
      onLockDurationChange={handleLockDurationChange}
      onReminderDaysChange={handleReminderDaysChange}
      onSave={handleSaveSettings}
    />
  );
};

export default SecuritySettingsPage;
