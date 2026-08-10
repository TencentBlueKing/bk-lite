'use client';

import React from 'react';
import { Alert, Skeleton } from 'antd';
import { useTranslation } from '@/utils/i18n';

interface PasswordPolicyNoticeProps {
  className?: string;
  loading?: boolean;
  minLength: number;
  maxLength: number;
  requiredCharTypes: readonly string[];
}

const PasswordPolicyNotice: React.FC<PasswordPolicyNoticeProps> = ({
  className,
  loading = false,
  minLength,
  maxLength,
  requiredCharTypes,
}) => {
  const { t } = useTranslation();

  if (loading) {
    return <Skeleton active paragraph={{ rows: 2 }} className={className} />;
  }

  const typeLabels: Record<string, string> = {
    uppercase: t('system.security.requireUppercase'),
    lowercase: t('system.security.requireLowercase'),
    digit: t('system.security.requireDigit'),
    special: t('system.security.requireSpecial'),
  };

  return (
    <Alert
      message={
        <div>
          <div className="mb-1 font-semibold">
            {t('system.security.passwordLengthRange')}: {minLength}-{maxLength}
          </div>
          <div className="text-xs">
            {t('system.security.passwordComplexity')}:{' '}
            {requiredCharTypes.map((type) => typeLabels[type]).join('、')}
          </div>
        </div>
      }
      type="info"
      showIcon
      className={className}
    />
  );
};

export default PasswordPolicyNotice;
