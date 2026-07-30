'use client';

import React, { useEffect, useState } from 'react';
import { message } from 'antd';
import { useSecurityApi } from '@/app/system-manager/api/security';
import LoginSettings from '@/app/system-manager/components/security/authSettings';
import { useTranslation } from '@/utils/i18n';

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
  const [initialPasswordEnabled, setInitialPasswordEnabled] = useState(false);
  const [pendingInitialPasswordEnabled, setPendingInitialPasswordEnabled] = useState(false);
  const [initialPasswordConfigured, setInitialPasswordConfigured] = useState(false);
  const [initialPasswordEditing, setInitialPasswordEditing] = useState(false);
  const [initialPassword, setInitialPassword] = useState('');
  const [confirmInitialPassword, setConfirmInitialPassword] = useState('');

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

      const initialPasswordEnabledValue = settings.user_create_initial_password_enabled === '1';
      setInitialPasswordEnabled(initialPasswordEnabledValue);
      setPendingInitialPasswordEnabled(initialPasswordEnabledValue);
      setInitialPasswordConfigured(settings.user_create_initial_password_configured === '1');
      setInitialPasswordEditing(false);
      setInitialPassword('');
      setConfirmInitialPassword('');
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

  const handleInitialPasswordEnabledChange = (enabled: boolean) => {
    setPendingInitialPasswordEnabled(enabled);
    setInitialPasswordEditing(enabled && !initialPasswordConfigured);
    if (!enabled) {
      setInitialPassword('');
      setConfirmInitialPassword('');
    }
  };

  const initialPasswordRequired = pendingInitialPasswordEnabled && (
    !initialPasswordEnabled
    || pendingMinimumLength !== minimumLength
    || pendingMaximumLength !== maximumLength
    || pendingPasswordComplexity.join(',') !== passwordComplexity.join(',')
  );

  const handleSaveSettings = async () => {
    if (initialPasswordRequired && !initialPassword) {
      message.error(t('system.security.initialPasswordRequired'));
      return;
    }
    if (initialPassword && initialPassword !== confirmInitialPassword) {
      message.error(t('system.security.initialPasswordMismatch'));
      return;
    }
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
        userCreateInitialPasswordEnabled: pendingInitialPasswordEnabled ? '1' : '0',
        userCreateInitialPassword: initialPassword || undefined,
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
      setInitialPasswordEnabled(pendingInitialPasswordEnabled);
      setInitialPasswordConfigured(pendingInitialPasswordEnabled);
      setInitialPasswordEditing(false);
      setInitialPassword('');
      setConfirmInitialPassword('');
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
      setPendingInitialPasswordEnabled(initialPasswordEnabled);
      setInitialPasswordEditing(false);
      setInitialPassword('');
      setConfirmInitialPassword('');
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
      initialPasswordEnabled={pendingInitialPasswordEnabled}
      initialPasswordConfigured={initialPasswordConfigured}
      initialPasswordRequired={initialPasswordRequired}
      initialPasswordEditing={initialPasswordEditing}
      initialPassword={initialPassword}
      confirmInitialPassword={confirmInitialPassword}
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
      onInitialPasswordEnabledChange={handleInitialPasswordEnabledChange}
      onStartInitialPasswordChange={() => setInitialPasswordEditing(true)}
      onInitialPasswordChange={setInitialPassword}
      onConfirmInitialPasswordChange={setConfirmInitialPassword}
      onSave={handleSaveSettings}
    />
  );
};

export default SecuritySettingsPage;
