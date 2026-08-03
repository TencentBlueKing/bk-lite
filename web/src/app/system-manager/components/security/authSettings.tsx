'use client';

import React from 'react';
import { Alert, Switch, Input, InputNumber, Button, Select, Checkbox, Radio } from 'antd';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';

type InitialPasswordMode = 'fixed' | 'random' | 'none';

interface LoginSettingsProps {
  otpEnabled: boolean;
  loginExpiredTime: string;
  passwordExpiration: string;
  passwordComplexity: string[];
  minimumLength: string;
  maximumLength: string;
  loginAttempts: string;
  lockDuration: string;
  reminderDays: string;
  initialPasswordConfigured: boolean;
  initialPasswordRequired: boolean;
  initialPasswordEditing: boolean;
  initialPassword: string;
  confirmInitialPassword: string;
  initialPasswordMode: InitialPasswordMode;
  initialPasswordEmailChannelId: string;
  emailChannels: Array<{ id: number; name: string }>;
  emailChannelsError: boolean;
  loading: boolean;
  disabled?: boolean;
  onOtpChange: (checked: boolean) => void;
  onLoginExpiredTimeChange: (value: string) => void;
  onPasswordExpirationChange: (value: string) => void;
  onPasswordComplexityChange: (value: string[]) => void;
  onMinimumLengthChange: (value: string) => void;
  onMaximumLengthChange: (value: string) => void;
  onLoginAttemptsChange: (value: string) => void;
  onLockDurationChange: (value: string) => void;
  onReminderDaysChange: (value: string) => void;
  onInitialPasswordModeChange: (mode: InitialPasswordMode) => void;
  onInitialPasswordEmailChannelChange: (value: string) => void;
  onRetryEmailChannels: () => void;
  onStartInitialPasswordChange: () => void;
  onInitialPasswordChange: (value: string) => void;
  onConfirmInitialPasswordChange: (value: string) => void;
  onSave: () => void;
}

const LoginSettings: React.FC<LoginSettingsProps> = ({
  otpEnabled,
  loginExpiredTime,
  passwordExpiration,
  passwordComplexity,
  minimumLength,
  maximumLength,
  loginAttempts,
  lockDuration,
  reminderDays,
  initialPasswordConfigured,
  initialPasswordRequired,
  initialPasswordEditing,
  initialPassword,
  confirmInitialPassword,
  initialPasswordMode,
  initialPasswordEmailChannelId,
  emailChannels,
  emailChannelsError,
  loading,
  disabled = false,
  onOtpChange,
  onLoginExpiredTimeChange,
  onPasswordExpirationChange,
  onPasswordComplexityChange,
  onMinimumLengthChange,
  onMaximumLengthChange,
  onLoginAttemptsChange,
  onLockDurationChange,
  onReminderDaysChange,
  onInitialPasswordModeChange,
  onInitialPasswordEmailChannelChange,
  onRetryEmailChannels,
  onStartInitialPasswordChange,
  onInitialPasswordChange,
  onConfirmInitialPasswordChange,
  onSave
}) => {
  const { t } = useTranslation();
  const initialPasswordEmailChannelSelector = (
    <>
      <div className="flex items-center">
        <span className="text-xs mr-4 w-40 shrink-0">{t('system.security.initialPasswordEmailChannel')}</span>
        <Select
          style={{ width: 288 }}
          value={initialPasswordEmailChannelId || undefined}
          onChange={onInitialPasswordEmailChannelChange}
          disabled={disabled || loading}
          placeholder={t('system.security.initialPasswordEmailChannelPlaceholder')}
          options={emailChannels.map((channel) => ({ value: String(channel.id), label: channel.name }))}
        />
      </div>
      {emailChannelsError && (
        <div className="ml-44" style={{ maxWidth: 288 }}>
          <Alert
            type="error"
            showIcon
            message={t('system.security.initialPasswordEmailChannelLoadFailed')}
            action={<Button type="link" size="small" onClick={onRetryEmailChannels}>{t('system.security.initialPasswordEmailChannelRetry')}</Button>}
          />
        </div>
      )}
      <div className="flex">
        <span className="text-xs mr-4 w-40 shrink-0" />
        <p className="text-xs text-[var(--color-text-2)] leading-5">
          {t('system.security.initialPasswordEmailChannelNotice')}
        </p>
      </div>
    </>
  );

  return (
    <div className="bg-(--color-bg) p-4 rounded-lg shadow-sm mb-4">
      <h3 className="text-base font-semibold mb-4">{t('system.security.loginSettings')}</h3>
      <div className="flex items-center mb-4">
        <span className="text-xs mr-4">{t('system.security.otpSetting')}</span>
        <Switch
          size="small"
          checked={otpEnabled}
          onChange={onOtpChange}
          loading={loading}
          disabled={disabled}
        />
      </div>
      <div className="flex items-center mb-4">
        <span className="text-xs mr-4">{t('system.security.loginExpiredTime')}</span>
        <InputNumber
          stringMode
          min="0.1"
          step="0.1"
          value={loginExpiredTime}
          onChange={(value) => onLoginExpiredTimeChange(value || '24')}
          disabled={disabled || loading}
          addonAfter={t('system.security.hours')}
          style={{ width: '180px' }}
        />
      </div>

      <h3 className="text-base font-semibold mb-4 mt-6">{t('system.security.passwordSettings')}</h3>
      <div className="flex gap-8">
        {/* 左列 */}
        <div className="flex-1">
          <div className="flex items-center mb-4">
            <span className="text-xs mr-4 w-32">{t('system.security.passwordLengthRange')}</span>
            <div className="flex items-center gap-2">
              <Select
                value={minimumLength}
                onChange={onMinimumLengthChange}
                disabled={disabled || loading}
                style={{ width: '80px' }}
                options={[
                  { value: '8', label: '8' },
                  { value: '10', label: '10' },
                  { value: '12', label: '12' },
                ]}
              />
              <span className="text-xs">{t('system.security.to')}</span>
              <Select
                value={maximumLength}
                onChange={onMaximumLengthChange}
                disabled={disabled || loading}
                style={{ width: '80px' }}
                options={[
                  { value: '16', label: '16' },
                  { value: '18', label: '18' },
                  { value: '20', label: '20' },
                  { value: '24', label: '24' },
                  { value: '32', label: '32' },
                ]}
              />
            </div>
          </div>
          <div className="flex items-start mb-4">
            <span className="text-xs mr-4 w-32 mt-1">{t('system.security.passwordComplexity')}</span>
            <Checkbox.Group
              value={passwordComplexity}
              onChange={onPasswordComplexityChange}
              disabled={disabled || loading}
            >
              <div className="flex flex-col gap-2">
                <Checkbox value="uppercase">{t('system.security.requireUppercase')}</Checkbox>
                <Checkbox value="lowercase">{t('system.security.requireLowercase')}</Checkbox>
                <Checkbox value="digit">{t('system.security.requireDigit')}</Checkbox>
                <Checkbox value="special">{t('system.security.requireSpecial')}</Checkbox>
              </div>
            </Checkbox.Group>
          </div>
          <div className="flex items-center mb-4">
            <span className="text-xs mr-4 w-32">{t('system.security.passwordExpiration')}</span>
            <Select
              value={passwordExpiration}
              onChange={onPasswordExpirationChange}
              disabled={disabled || loading}
              style={{ width: '180px' }}
              options={[
                { value: '30', label: t('system.security.oneMonth') },
                { value: '90', label: t('system.security.threeMonths') },
                { value: '180', label: t('system.security.sixMonths') },
                { value: '365', label: t('system.security.oneYear') },
                { value: '0', label: t('system.security.permanent') },
              ]}
            />
          </div>
          <div className="flex items-center mb-4">
            <span className="text-xs mr-4 w-32">{t('system.security.loginAttempts')}</span>
            <Select
              value={loginAttempts}
              onChange={onLoginAttemptsChange}
              disabled={disabled || loading}
              style={{ width: '180px' }}
              options={[
                { value: '3', label: t('system.security.threeTimes') },
                { value: '5', label: t('system.security.fiveTimes') },
              ]}
            />
          </div>
        </div>

        {/* 右列 */}
        <div className="flex-1">
          <div className="flex items-center mb-4">
            <span className="text-xs mr-4 w-40">{t('system.security.lockDuration')}</span>
            <InputNumber
              min="60"
              value={lockDuration}
              onChange={(value) => onLockDurationChange(value?.toString() || '180')}
              disabled={disabled || loading}
              addonAfter={t('system.security.seconds')}
              style={{ width: '180px' }}
            />
          </div>
          <div className="flex items-center mb-4">
            <span className="text-xs mr-4 w-40">{t('system.security.reminderDays')}</span>
            <InputNumber
              min="1"
              max="30"
              value={reminderDays}
              onChange={(value) => onReminderDaysChange(value?.toString() || '7')}
              disabled={disabled || loading}
              addonAfter={t('system.security.days')}
              style={{ width: '180px' }}
            />
          </div>
        </div>
      </div>

      <section className="mt-6 border-t border-[var(--color-border-1)] pt-4 space-y-4" aria-labelledby="initial-password-heading">
        <div>
          <h4 id="initial-password-heading" className="text-sm font-semibold text-[var(--color-text-1)]">
            {t('system.security.newUserInitialPassword')}
          </h4>
          <p className="mt-1 text-xs text-[var(--color-text-2)]">
            {t('system.security.newUserInitialPasswordDescription')}
          </p>
        </div>

        <div className="flex items-center">
          <span className="text-xs mr-4 w-40 shrink-0">{t('system.security.initialPasswordModeLabel')}</span>
          <Radio.Group
            value={initialPasswordMode}
            onChange={(event) => onInitialPasswordModeChange(event.target.value as InitialPasswordMode)}
            disabled={disabled || loading}
          >
            <Radio value="fixed">{t('system.security.initialPasswordModeFixed')}</Radio>
            <Radio value="random">{t('system.security.initialPasswordModeRandom')}</Radio>
            <Radio value="none">{t('system.security.initialPasswordModeNone')}</Radio>
          </Radio.Group>
        </div>

        {initialPasswordMode === 'random' && (
          initialPasswordEmailChannelSelector
        )}

        {initialPasswordMode === 'fixed' && (
          <>
            {initialPasswordConfigured && !initialPasswordRequired && !initialPasswordEditing && (
              <div className="flex items-center">
                <span className="text-xs mr-4 w-40 shrink-0">{t('system.security.initialPassword')}</span>
                <span className="inline-flex items-center gap-2 text-xs text-[var(--color-text-2)]">
                  <span>{t('system.security.initialPasswordConfigured')}</span>
                  <Button type="link" size="small" className="p-0" onClick={onStartInitialPasswordChange}>
                    {t('system.security.changeInitialPassword')}
                  </Button>
                </span>
              </div>
            )}
            {initialPasswordEmailChannelSelector}
            {(initialPasswordRequired || !initialPasswordConfigured || initialPasswordEditing) && (
              <>
                {initialPasswordRequired && (
                  <div className="flex">
                    <span className="text-xs mr-4 w-40 shrink-0" />
                    <div className="text-xs text-[var(--color-warning)]">{t('system.security.initialPasswordReentryRequired')}</div>
                  </div>
                )}
                <div className="flex items-center">
                  <span className="text-xs mr-4 w-40 shrink-0">{t('system.security.initialPassword')}</span>
                  <Input.Password
                    style={{ width: 288 }}
                    value={initialPassword}
                    onChange={(event) => onInitialPasswordChange(event.target.value)}
                    disabled={disabled || loading}
                    autoComplete="new-password"
                    placeholder={t('system.security.initialPasswordPlaceholder')}
                  />
                </div>
                <div className="flex items-center">
                  <span className="text-xs mr-4 w-40 shrink-0">{t('system.security.confirmInitialPassword')}</span>
                  <Input.Password
                    style={{ width: 288 }}
                    value={confirmInitialPassword}
                    onChange={(event) => onConfirmInitialPasswordChange(event.target.value)}
                    disabled={disabled || loading}
                    autoComplete="new-password"
                    placeholder={t('system.security.confirmInitialPasswordPlaceholder')}
                  />
                </div>
                <div className="flex">
                  <span className="text-xs mr-4 w-40 shrink-0" />
                  <p className="text-xs text-[var(--color-text-2)] leading-5">
                    {t('system.security.initialPasswordDeliveryNotice')}
                  </p>
                </div>
              </>
            )}
          </>
        )}

        {initialPasswordMode === 'none' && (
          <div className="flex">
            <span className="text-xs mr-4 w-40 shrink-0" />
            <p className="text-xs text-[var(--color-text-2)] leading-5">
              {t('system.security.initialPasswordNoneNotice')}
            </p>
          </div>
        )}
      </section>

      <div className="mt-6">
        <PermissionWrapper requiredPermissions={['Edit']}>
          <Button
            type="primary"
            onClick={onSave}
            loading={loading}
          >
            {t('common.save')}
          </Button>
        </PermissionWrapper>
      </div>
    </div>
  );
};

export default LoginSettings;
