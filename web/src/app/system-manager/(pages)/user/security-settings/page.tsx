'use client';

import React, { useEffect, useState } from 'react';
import { message } from 'antd';
import { useSecurityApi } from '@/app/system-manager/api/security';
import { useChannelApi } from '@/app/system-manager/api/channel';
import LoginSettings from '@/app/system-manager/components/security/authSettings';
import { useTranslation } from '@/utils/i18n';

type InitialPasswordMode = 'fixed' | 'random' | 'none';

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
  const [initialPasswordConfigured, setInitialPasswordConfigured] = useState(false);
  const [initialPasswordEditing, setInitialPasswordEditing] = useState(false);
  const [initialPassword, setInitialPassword] = useState('');
  const [confirmInitialPassword, setConfirmInitialPassword] = useState('');
  // 新增:本地用户初始密码 mode (对齐用户同步处的 fixed/random/none)
  const [initialPasswordMode, setInitialPasswordMode] = useState<InitialPasswordMode>('fixed');
  const [pendingInitialPasswordMode, setPendingInitialPasswordMode] = useState<InitialPasswordMode>('fixed');
  // random 模式所需的邮件通道
  const [initialPasswordEmailChannelId, setInitialPasswordEmailChannelId] = useState<string>('');
  const [pendingInitialPasswordEmailChannelId, setPendingInitialPasswordEmailChannelId] = useState<string>('');
  const [emailChannels, setEmailChannels] = useState<Array<{ id: number; name: string }>>([]);
  const [emailChannelsError, setEmailChannelsError] = useState(false);

  const { getSystemSettings, updateOtpSettings } = useSecurityApi();
  const { getChannelData } = useChannelApi();

  useEffect(() => {
    fetchSystemSettings();
    fetchEmailChannels();
  }, []);

  const fetchEmailChannels = async () => {
    try {
      setEmailChannelsError(false);
      const res = await getChannelData({ channel_type: 'email', page_size: 200 });
      const items = Array.isArray(res?.items) ? res.items : Array.isArray(res) ? res : [];
      setEmailChannels(items.map((item: { id: number; name: string }) => ({ id: item.id, name: item.name })));
    } catch (error) {
      console.error('Failed to fetch email channels:', error);
      setEmailChannels([]);
      setEmailChannelsError(true);
    }
  };

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

      const mode = (settings.user_create_initial_password_mode || 'fixed') as InitialPasswordMode;
      setInitialPasswordMode(mode);
      setPendingInitialPasswordMode(mode);
      const channelId = String(settings.user_create_initial_password_random_email_channel_id || '');
      setInitialPasswordEmailChannelId(channelId);
      setPendingInitialPasswordEmailChannelId(channelId);

      setInitialPasswordConfigured(mode === 'fixed' && settings.user_create_initial_password_configured === '1');
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

  const handleInitialPasswordModeChange = (mode: InitialPasswordMode) => {
    setPendingInitialPasswordMode(mode);
    if (mode !== 'fixed') {
      // random/none 模式下清空固定密码输入,避免历史 hash 被误回显
      setInitialPassword('');
      setConfirmInitialPassword('');
      setInitialPasswordEditing(false);
    }
  };

  const handleInitialPasswordEmailChannelChange = (value: string) => {
    setPendingInitialPasswordEmailChannelId(value);
  };

  const initialPasswordRequired = pendingInitialPasswordMode === 'fixed' && (
    !initialPasswordConfigured
    || pendingMinimumLength !== minimumLength
    || pendingMaximumLength !== maximumLength
    || pendingPasswordComplexity.join(',') !== passwordComplexity.join(',')
  );

  const handleSaveSettings = async () => {
    if (pendingInitialPasswordMode === 'fixed' && initialPasswordRequired && !initialPassword) {
      message.error(t('system.security.initialPasswordRequired'));
      return;
    }
    if (initialPassword && initialPassword !== confirmInitialPassword) {
      message.error(t('system.security.initialPasswordMismatch'));
      return;
    }
    const initialPasswordActive = pendingInitialPasswordMode === 'random'
      || pendingInitialPasswordMode === 'fixed';
    if (initialPasswordActive && !pendingInitialPasswordEmailChannelId) {
      message.error(t('system.security.initialPasswordEmailChannelRequired'));
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
        userCreateInitialPasswordMode: pendingInitialPasswordMode,
        userCreateInitialPassword: initialPassword || undefined,
        userCreateInitialPasswordEmailChannelId:
          pendingInitialPasswordMode !== 'none' ? pendingInitialPasswordEmailChannelId : undefined,
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
      setInitialPasswordMode(pendingInitialPasswordMode);
      setInitialPasswordEmailChannelId(pendingInitialPasswordEmailChannelId);
      setInitialPasswordConfigured(pendingInitialPasswordMode === 'fixed');
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
      setPendingInitialPasswordMode(initialPasswordMode);
      setPendingInitialPasswordEmailChannelId(initialPasswordEmailChannelId);
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
      initialPasswordConfigured={initialPasswordConfigured}
      initialPasswordRequired={initialPasswordRequired}
      initialPasswordEditing={initialPasswordEditing}
      initialPassword={initialPassword}
      confirmInitialPassword={confirmInitialPassword}
      initialPasswordMode={pendingInitialPasswordMode}
      initialPasswordEmailChannelId={pendingInitialPasswordEmailChannelId}
      emailChannels={emailChannels}
      emailChannelsError={emailChannelsError}
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
      onInitialPasswordModeChange={handleInitialPasswordModeChange}
      onInitialPasswordEmailChannelChange={handleInitialPasswordEmailChannelChange}
      onRetryEmailChannels={fetchEmailChannels}
      onStartInitialPasswordChange={() => setInitialPasswordEditing(true)}
      onInitialPasswordChange={setInitialPassword}
      onConfirmInitialPasswordChange={setConfirmInitialPassword}
      onSave={handleSaveSettings}
    />
  );
};

export default SecuritySettingsPage;
