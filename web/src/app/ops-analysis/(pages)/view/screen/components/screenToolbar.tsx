'use client';

import React from 'react';
import { Button, Space, Tooltip } from 'antd';
import {
  EditOutlined,
  FilterOutlined,
  FullscreenOutlined,
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import PermissionWrapper from '@/components/permission';
import { useTranslation } from '@/utils/i18n';
import type { DirItem } from '@/app/ops-analysis/types';

interface ScreenToolbarProps {
  selectedScreen?: DirItem | null;
  editMode: boolean;
  onOpenSettings: () => void;
  onOpenFilterConfig: () => void;
  onOpenWidgetSelector: () => void;
  onPreview: () => void;
  onRefresh: () => void;
  onEdit: () => void;
  onCancel: () => void;
  onSave: () => void;
  saving?: boolean;
}

const ScreenToolbar: React.FC<ScreenToolbarProps> = ({
  selectedScreen,
  editMode,
  onOpenSettings,
  onOpenFilterConfig,
  onOpenWidgetSelector,
  onPreview,
  onRefresh,
  onEdit,
  onCancel,
  onSave,
  saving = false,
}) => {
  const { t } = useTranslation();
  const iconButtonClassName =
    'rounded-full! h-8 w-8 min-w-8 flex items-center justify-center';

  return (
    <Space>
      <Tooltip title={t('common.refresh')}>
        <Button
          type="text"
          icon={<ReloadOutlined />}
          aria-label={t('common.refresh')}
          className={iconButtonClassName}
          onClick={onRefresh}
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
      {editMode && (
        <>
          <Tooltip title={t('opsAnalysis.screen.canvasSettings')}>
            <Button
              type="text"
              icon={<SettingOutlined />}
              aria-label={t('opsAnalysis.screen.canvasSettings')}
              className={iconButtonClassName}
              onClick={onOpenSettings}
            />
          </Tooltip>
          <Button
            type="default"
            icon={<FilterOutlined />}
            className="rounded-full!"
            onClick={onOpenFilterConfig}
          >
            {t('dashboard.unifiedFilterConfig')}
          </Button>
          <Button
            type="default"
            icon={<PlusOutlined />}
            className="rounded-full!"
            onClick={onOpenWidgetSelector}
          >
            {t('opsAnalysis.screen.addWidget')}
          </Button>
        </>
      )}
      <PermissionWrapper requiredPermissions={['EditChart']}>
        {!editMode ? (
          <Tooltip title={t('common.edit')}>
            <Button
              type="text"
              icon={<EditOutlined />}
              aria-label={t('common.edit')}
              disabled={!selectedScreen?.data_id || selectedScreen?.is_build_in}
              className={iconButtonClassName}
              onClick={onEdit}
            />
          </Tooltip>
        ) : (
          <div className="ml-2 flex items-center gap-2">
            <Button className="rounded-full!" onClick={onCancel}>
              {t('common.cancel')}
            </Button>
            <Button
              type="primary"
              loading={saving}
              className="rounded-full!"
              onClick={onSave}
            >
              {t('common.save')}
            </Button>
          </div>
        )}
      </PermissionWrapper>
    </Space>
  );
};

export default ScreenToolbar;
