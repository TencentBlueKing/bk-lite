'use client';

import { ReloadOutlined } from '@ant-design/icons';
import { Alert, Button } from 'antd';

import { useTranslation } from '@/utils/i18n';

/** Error chrome with explicit retry (web/DESIGN.md States + Do's). */
export default function RumPageError({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Alert
      type="error"
      showIcon
      role="alert"
      message={message}
      action={
        onRetry ? (
          <Button icon={<ReloadOutlined />} onClick={onRetry}>
            {t('rum.common.retry', '重试')}
          </Button>
        ) : undefined
      }
    />
  );
}
