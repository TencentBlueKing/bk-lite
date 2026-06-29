'use client';

import React from 'react';
import { Button, Space, Tooltip } from 'antd';
import { FullscreenOutlined, SettingOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

interface ScreenToolbarProps {
  onOpenSettings: () => void;
  onPreview: () => void;
  saving?: boolean;
}

const ScreenToolbar: React.FC<ScreenToolbarProps> = ({
  onOpenSettings,
  onPreview,
  saving = false,
}) => {
  const { t } = useTranslation();
  const iconButtonClassName =
    'rounded-full! h-8 w-8 min-w-8 flex items-center justify-center';

  return (
    <Space>
      <Tooltip title={t('opsAnalysis.screen.canvasSettings')}>
        <Button
          type="text"
          icon={<SettingOutlined />}
          loading={saving}
          aria-label={t('opsAnalysis.screen.canvasSettings')}
          className={iconButtonClassName}
          onClick={onOpenSettings}
        />
      </Tooltip>
      <Tooltip title={t('opsAnalysis.screen.fullscreenPreview')}>
        <Button
          type="text"
          icon={<FullscreenOutlined />}
          aria-label={t('opsAnalysis.screen.fullscreenPreview')}
          className={iconButtonClassName}
          onClick={onPreview}
        />
      </Tooltip>
    </Space>
  );
};

export default ScreenToolbar;
