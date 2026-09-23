'use client';

import type { MouseEventHandler } from 'react';
import { ReloadOutlined } from '@ant-design/icons';
import { Button } from 'antd';

import { useTranslation } from '@/utils/i18n';

/** RUM 列表/详情统一刷新：图标 + 「刷新」文案。 */
export default function RumRefreshButton({
  onClick,
  loading,
  disabled,
  className,
}: {
  onClick?: MouseEventHandler<HTMLElement>;
  loading?: boolean;
  disabled?: boolean;
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <Button
      icon={<ReloadOutlined aria-hidden="true" />}
      loading={loading}
      disabled={disabled}
      onClick={onClick}
      className={className}
    >
      {t('rum.common.refresh', '刷新')}
    </Button>
  );
}
