'use client';

import React from 'react';
import { Button, Tooltip } from 'antd';
import {
  EditOutlined,
  FullscreenOutlined,
  MailOutlined,
  RedoOutlined,
  ReloadOutlined,
  SettingOutlined,
  ShareAltOutlined,
  UndoOutlined,
} from '@ant-design/icons';
import Icon from '@/components/icon';
import PermissionWrapper from '@/components/permission';
import TimeSelector from '@/components/time-selector';
import { useTranslation } from '@/utils/i18n';
import type { DirItem } from '@/app/ops-analysis/types';

interface ScreenToolbarProps {
  selectedScreen?: DirItem | null;
  editMode: boolean;
  shareMode?: boolean;
  shareLoading?: boolean;
  onOpenShare?: () => void;
  onOpenSubscription?: () => void;
  onOpenSettings: () => void;
  onOpenFilterConfig: () => void;
  onPreview: () => void;
  onRefresh: () => void;
  frequenceValue?: number;
  onFrequencyChange?: (intervalMs: number) => void;
  onEdit: () => void;
  onCancel: () => void;
  onSave: () => void;
  saving?: boolean;
  editExtra?: React.ReactNode;
  canUndo?: boolean;
  canRedo?: boolean;
  onUndo?: () => void;
  onRedo?: () => void;
}

const ScreenToolbar: React.FC<ScreenToolbarProps> = ({
  selectedScreen,
  editMode,
  shareMode = false,
  shareLoading = false,
  onOpenShare,
  onOpenSubscription,
  onOpenSettings,
  onOpenFilterConfig,
  onPreview,
  onRefresh,
  frequenceValue = 0,
  onFrequencyChange,
  onEdit,
  onCancel,
  onSave,
  saving = false,
  editExtra,
  canUndo = false,
  canRedo = false,
  onUndo,
  onRedo,
}) => {
  const { t } = useTranslation();
  const iconButtonClassName =
    'rounded-full! h-8 w-8 min-w-8 flex items-center justify-center';
  const iconClassName = 'text-[16px]';

  if (!shareMode && editMode) {
    return (
      <div className="flex items-center gap-2" data-export-hidden="true">
        <div className="flex items-center gap-0.5">
          {onUndo && onRedo ? (
            <>
              <Tooltip title={t('opsAnalysis.screen.undo')}>
                <Button
                  type="text"
                  icon={<UndoOutlined className={iconClassName} />}
                  aria-label={t('opsAnalysis.screen.undo')}
                  onClick={onUndo}
                  disabled={!canUndo}
                  className={iconButtonClassName}
                />
              </Tooltip>
              <Tooltip title={t('opsAnalysis.screen.redo')}>
                <Button
                  type="text"
                  icon={<RedoOutlined className={iconClassName} />}
                  aria-label={t('opsAnalysis.screen.redo')}
                  onClick={onRedo}
                  disabled={!canRedo}
                  className={iconButtonClassName}
                />
              </Tooltip>
            </>
          ) : null}
          <Tooltip title={t('opsAnalysis.screen.canvasSettings')}>
            <Button
              type="text"
              icon={<SettingOutlined className={iconClassName} />}
              aria-label={t('opsAnalysis.screen.canvasSettings')}
              onClick={onOpenSettings}
              className={iconButtonClassName}
            />
          </Tooltip>
          <Tooltip title={t('opsAnalysis.screen.fullscreenPreview')}>
            <Button
              type="text"
              icon={<FullscreenOutlined className={iconClassName} />}
              aria-label={t('opsAnalysis.screen.fullscreenPreview')}
              onClick={onPreview}
              className={iconButtonClassName}
            />
          </Tooltip>
          <Tooltip title={t('common.refresh')}>
            <Button
              type="text"
              icon={<ReloadOutlined className={iconClassName} />}
              aria-label={t('common.refresh')}
              onClick={onRefresh}
              className={iconButtonClassName}
            />
          </Tooltip>
          <Tooltip title={t('dashboard.configUnifiedFilterFields')}>
            <Button
              type="text"
              icon={<Icon type="shaixuantiaojian" style={{ fontSize: 20 }} />}
              aria-label={t('dashboard.configUnifiedFilterFields')}
              onClick={onOpenFilterConfig}
              className={iconButtonClassName}
            />
          </Tooltip>
        </div>

        <PermissionWrapper requiredPermissions={['EditChart']}>
          <div className="flex items-center gap-2">
            {editExtra}
            <Button type="default" onClick={onCancel}>
              {t('common.cancel')}
            </Button>
            <Button type="primary" loading={saving} onClick={onSave}>
              {t('common.save')}
            </Button>
          </div>
        </PermissionWrapper>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      <TimeSelector
        onlyRefresh
        frequenceValue={frequenceValue}
        onRefresh={onRefresh}
        onFrequenceChange={onFrequencyChange}
      />
      <Tooltip title={t('opsAnalysis.screen.fullscreenPreview')}>
        <Button
          type="text"
          icon={<FullscreenOutlined className={iconClassName} />}
          aria-label={t('opsAnalysis.screen.fullscreenPreview')}
          className={iconButtonClassName}
          onClick={onPreview}
        />
      </Tooltip>
      {!shareMode && onOpenShare && (
        <Tooltip title={t('dashboard.share')}>
          <Button
            type="text"
            icon={<ShareAltOutlined className={iconClassName} />}
            loading={shareLoading}
            disabled={shareLoading}
            aria-label={t('dashboard.share')}
            className={iconButtonClassName}
            onClick={onOpenShare}
          />
        </Tooltip>
      )}
      {!shareMode && onOpenSubscription && (
        <Tooltip title={t('dashboard.subscriptionTitle')}>
          <Button
            type="text"
            icon={<MailOutlined className={iconClassName} />}
            aria-label={t('dashboard.subscriptionTitle')}
            className={iconButtonClassName}
            onClick={onOpenSubscription}
          />
        </Tooltip>
      )}
      {!shareMode && (
        <PermissionWrapper requiredPermissions={['EditChart']}>
          <Tooltip title={t('common.edit')}>
            <Button
              type="text"
              icon={<EditOutlined className={iconClassName} />}
              aria-label={t('common.edit')}
              disabled={!selectedScreen?.data_id || selectedScreen?.is_build_in}
              className={iconButtonClassName}
              onClick={onEdit}
            />
          </Tooltip>
        </PermissionWrapper>
      )}
    </div>
  );
};

export default ScreenToolbar;
