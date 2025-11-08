'use client';

import React from 'react';
import { Switch, InputNumber, Button } from 'antd';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';

interface LoginSettingsProps {
  otpEnabled: boolean;
  loginExpiredTime: string;
  loading: boolean;
  onOtpChange: (checked: boolean) => void;
  onLoginExpiredTimeChange: (value: string) => void;
  onSave: () => void;
}

const LoginSettings: React.FC<LoginSettingsProps> = ({
  otpEnabled,
  loginExpiredTime,
  loading,
  onOtpChange,
  onLoginExpiredTimeChange,
  onSave
}) => {
  const { t } = useTranslation();

  return (
    <div className="bg-[var(--color-bg)] p-4 rounded-lg shadow-sm mb-4">
      <h3 className="text-base font-semibold mb-4">{t('system.security.loginSettings')}</h3>
      <div className="flex items-center mb-4">
        <span className="text-xs mr-4">{t('system.security.otpSetting')}</span>
        <Switch 
          size="small" 
          checked={otpEnabled} 
          onChange={onOtpChange}
          loading={loading}
        />
      </div>
      <div className="flex items-center mb-4">
        <span className="text-xs mr-4">{t('system.security.loginExpiredTime')}</span>
        <InputNumber
          min="1"
          value={loginExpiredTime}
          onChange={(value) => onLoginExpiredTimeChange(value?.toString() || '24')}
          disabled={loading}
          addonAfter={t('system.security.hours')}
          style={{ width: '180px' }}                           
        />
      </div>
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
