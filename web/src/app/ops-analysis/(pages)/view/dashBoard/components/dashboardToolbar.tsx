import React from 'react';
import { Button, Tooltip } from 'antd';
import {
  DownloadOutlined,
  EditOutlined,
  FullscreenOutlined,
  MailOutlined,
  PlusOutlined,
  ReloadOutlined,
  ShareAltOutlined,
} from '@ant-design/icons';

import type { DirItem } from '@/app/ops-analysis/types';
import Icon from '@/components/icon';
import PermissionWrapper from '@/components/permission';
import TimeSelector from '@/components/time-selector';
import { useTranslation } from '@/utils/i18n';

interface DashboardToolbarProps {
  selectedDashboard?: DirItem | null;
  chartTheme: {
    panelBg: string;
    panelBorderColor: string;
  };
  exporting: boolean;
  isFullscreen: boolean;
  isEditMode: boolean;
  saving: boolean;
  onRefresh: () => void;
  frequenceValue?: number;
  onFrequencyChange?: (intervalMs: number) => void;
  onToggleFullscreen: () => void;
  onExportPdf: () => void;
  onOpenFilterConfig: () => void;
  onOpenAddView: () => void;
  onOpenAddGroup: () => void;
  onToggleEditMode: () => void;
  onCancelEdit: () => void;
  onSave: () => void;
  editExtra?: React.ReactNode;
  shareMode?: boolean;
  shareLoading?: boolean;
  onOpenShare?: () => void;
  onOpenSubscriptions?: () => void;
}

const DashboardToolbar: React.FC<DashboardToolbarProps> = ({
  selectedDashboard,
  chartTheme,
  exporting,
  isFullscreen,
  isEditMode,
  saving,
  onRefresh,
  frequenceValue = 0,
  onFrequencyChange,
  onToggleFullscreen,
  onExportPdf,
  onOpenFilterConfig,
  onOpenAddView,
  onOpenAddGroup,
  onToggleEditMode,
  onCancelEdit,
  onSave,
  editExtra,
  shareMode = false,
  shareLoading = false,
  onOpenShare,
  onOpenSubscriptions,
}) => {
  const { t } = useTranslation();
  const iconButtonClassName =
    'h-8 w-8 min-w-8 px-0! flex items-center justify-center';

  if (!shareMode && isEditMode) {
    const boxButtonStyle = {
      borderColor: chartTheme.panelBorderColor,
      color: 'var(--color-text-1)',
      background: chartTheme.panelBg,
    };

    return (
      <div className="flex items-center gap-2" data-export-hidden="true">
        <div className="flex items-center gap-0.5">
          <Tooltip title={t('common.fullscreen')}>
            <Button
              type="text"
              icon={<FullscreenOutlined style={{ fontSize: 16 }} />}
              aria-pressed={isFullscreen}
              onClick={onToggleFullscreen}
              className={iconButtonClassName}
            />
          </Tooltip>
          <Tooltip title={t('common.refresh')}>
            <Button
              type="text"
              icon={<ReloadOutlined style={{ fontSize: 16 }} />}
              aria-label={t('common.refresh')}
              onClick={onRefresh}
              className={iconButtonClassName}
            />
          </Tooltip>
          <PermissionWrapper requiredPermissions={['EditChart']}>
            <Tooltip title={t('dashboard.configUnifiedFilterFields')}>
              <Button
                type="text"
                icon={<Icon type="shaixuantiaojian" style={{ fontSize: 20 }} />}
                aria-label={t('dashboard.configUnifiedFilterFields')}
                onClick={onOpenFilterConfig}
                className={iconButtonClassName}
              />
            </Tooltip>
          </PermissionWrapper>
        </div>

        <PermissionWrapper requiredPermissions={['EditChart']}>
          <div className="flex items-center gap-2">
            {editExtra}
            <Button
              type="default"
              icon={<PlusOutlined />}
              onClick={onOpenAddView}
              style={boxButtonStyle}
            >
              {t('dashboard.viewShort')}
            </Button>
            <Button
              type="default"
              icon={<PlusOutlined />}
              onClick={onOpenAddGroup}
              style={boxButtonStyle}
            >
              {t('dashboard.groupShort')}
            </Button>
            <Button
              type="default"
              disabled={!selectedDashboard?.data_id}
              onClick={onCancelEdit}
              style={boxButtonStyle}
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="primary"
              loading={saving}
              disabled={!selectedDashboard?.data_id}
              onClick={onSave}
            >
              {t('common.save')}
            </Button>
          </div>
        </PermissionWrapper>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5" data-export-hidden="true">
      <TimeSelector
        onlyRefresh
        frequenceValue={frequenceValue}
        onRefresh={onRefresh}
        onFrequenceChange={onFrequencyChange}
      />

      <Tooltip title={t('common.fullscreen')}>
        <Button
          type="text"
          icon={<FullscreenOutlined style={{ fontSize: 16 }} />}
          aria-pressed={isFullscreen}
          onClick={onToggleFullscreen}
          className="rounded-full!"
        />
      </Tooltip>

      {!shareMode && (
        <>
          <Tooltip title={t('dashboard.exportPdf')}>
            <Button
              type="text"
              icon={<DownloadOutlined style={{ fontSize: 16 }} />}
              loading={exporting}
              onClick={onExportPdf}
              className="rounded-full!"
            />
          </Tooltip>
          {onOpenShare && (
            <Tooltip title={t('dashboard.share')}>
              <Button
                type="text"
                icon={<ShareAltOutlined />}
                loading={shareLoading}
                disabled={shareLoading}
                onClick={onOpenShare}
                className="rounded-full!"
              />
            </Tooltip>
          )}
          {onOpenSubscriptions && (
            <Tooltip title={t('dashboard.subscriptionTitle')}>
              <Button
                type="text"
                icon={<MailOutlined aria-hidden="true" />}
                aria-label={t('dashboard.subscriptionTitle')}
                onClick={onOpenSubscriptions}
                className="rounded-full!"
              />
            </Tooltip>
          )}
          <PermissionWrapper requiredPermissions={['EditChart']}>
            <Tooltip title={t('common.edit')}>
              <Button
                type="text"
                aria-label={t('common.edit')}
                icon={
                  <EditOutlined aria-hidden="true" style={{ fontSize: 16 }} />
                }
                disabled={
                  !selectedDashboard?.data_id || selectedDashboard?.is_build_in
                }
                onClick={onToggleEditMode}
                className="rounded-full!"
              />
            </Tooltip>
          </PermissionWrapper>
        </>
      )}
    </div>
  );
};

export default DashboardToolbar;
