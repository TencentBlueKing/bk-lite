'use client';

import React from 'react';
import { Alert, Form, Segmented } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { WinrmScheme } from '@/app/node-manager/utils/winrm';

interface WinrmSchemeFieldProps {
  value: WinrmScheme;
  onChange: (value: WinrmScheme) => void;
  className?: string;
}

const WinrmSchemeField: React.FC<WinrmSchemeFieldProps> = ({
  value,
  onChange,
  className
}) => {
  const { t } = useTranslation();

  return (
    <Form.Item
      className={className}
      label={t('node-manager.cloudregion.node.winrmScheme')}
    >
      <div className="flex max-w-[640px] flex-col items-start gap-3">
        <Segmented
          block
          className="w-44"
          value={value}
          onChange={(nextValue) => onChange(nextValue as WinrmScheme)}
          options={[
            {
              label: t('node-manager.cloudregion.node.winrmSchemeHttps'),
              value: 'https'
            },
            {
              label: t('node-manager.cloudregion.node.winrmSchemeHttp'),
              value: 'http'
            }
          ]}
        />
        {value === 'http' && (
          <Alert
            type="warning"
            showIcon
            message={t('node-manager.cloudregion.node.winrmHttpWarningTitle')}
            description={t('node-manager.cloudregion.node.winrmHttpWarningDesc')}
          />
        )}
      </div>
    </Form.Item>
  );
};

export default WinrmSchemeField;
