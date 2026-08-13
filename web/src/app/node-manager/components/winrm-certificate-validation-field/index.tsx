'use client';

import React from 'react';
import { Alert, Form, Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';

interface WinrmCertificateValidationFieldProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  className?: string;
}

const WinrmCertificateValidationField: React.FC<
  WinrmCertificateValidationFieldProps
> = ({ checked, onChange, className }) => {
  const { t } = useTranslation();
  const statusText = t(
    checked
      ? 'node-manager.cloudregion.node.winrmCertValidationEnabled'
      : 'node-manager.cloudregion.node.winrmCertValidationDisabled'
  );

  return (
    <Form.Item
      className={className}
      label={t('node-manager.cloudregion.node.winrmCertValidation')}
    >
      <div className="flex max-w-[640px] flex-col gap-3">
        <div className="flex min-h-8 items-center gap-3">
          <Switch
            aria-label={t(
              'node-manager.cloudregion.node.winrmCertValidation'
            )}
            checked={checked}
            onChange={onChange}
          />
          <span className="text-[14px] text-[var(--color-text-2)]">
            {statusText}
          </span>
        </div>
        {!checked && (
          <Alert
            type="warning"
            showIcon
            message={t(
              'node-manager.cloudregion.node.winrmCertValidationWarningTitle'
            )}
            description={t(
              'node-manager.cloudregion.node.winrmCertValidationWarningDesc'
            )}
          />
        )}
      </div>
    </Form.Item>
  );
};

export default WinrmCertificateValidationField;
