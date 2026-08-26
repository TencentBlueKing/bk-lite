import React from 'react';
import { Button, Tooltip } from 'antd';
import {
  DownloadOutlined,
  EditOutlined,
  FullscreenOutlined,
  MailOutlined,
  PlusOutlined,
  ShareAltOutlined,
  SettingOutlined,
} from '@ant-design/icons';

import type { DirItem } from '@/app/ops-analysis/types';
import PermissionWrapper from '@/components/permission';
import TimeSelector from '@/components/time-selector';
import { useTranslation } from '@/utils/i18n';

interface ReportToolbarProps {
  selectedReport?: DirItem | null;
  chartTheme: {
    panelBg: string;
    panelBorderColor: string;
  };
  exporting: boolean;
  isFullscreen: boolean;
  editing: boolean;
  saving: boolean;
  canEnterEdit: boolean;
  onRefresh: () => void;
  frequenceValue?: number;
  onFrequencyChange?: (intervalMs: number) => void;
  onToggleFullscreen: () => void;
  onExportPdf: () => void;
  onOpenFilterConfig: () => void;
  onOpenAddComponent: () => void;
  onToggleEditMode: () => void;
  onCancelEdit: () => void;
  onSave: () => void;
  editExtra?: React.ReactNode;
  shareMode?: boolean;
  shareLoading?: boolean;
  onOpenShare?: () => void;
  onOpenSubscriptions?: () => void;
}

const ReportToolbar: React.FC<ReportToolbarProps> = ({
  selectedReport,
  chartTheme,
  exporting,
  isFullscreen,
  editing,
  saving,
  canEnterEdit,
  onRefresh,
  frequenceValue = 0,
  onFrequencyChange,
  onToggleFullscreen,
  onExportPdf,
  onOpenFilterConfig,
  onOpenAddComponent,
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
          icon={<FullscreenOutlined className="text-base" />}
          aria-pressed={isFullscreen}
          aria-label={t('common.fullscreen')}
          onClick={onToggleFullscreen}
          className="rounded-full!"
        />
      </Tooltip>

      {!shareMode && !editing && (
        <Tooltip title={t('dashboard.exportPdf')}>
          <Button
            type="text"
            icon={<DownloadOutlined className="text-base" />}
            loading={exporting}
            aria-label={t('dashboard.exportPdf')}
            onClick={onExportPdf}
            className="rounded-full!"
          />
        </Tooltip>
      )}

      {!shareMode && !editing && onOpenShare && (
        <Tooltip title={t('dashboard.share')}>
          <Button
            type="text"
            icon={<ShareAltOutlined />}
            loading={shareLoading}
            disabled={shareLoading}
            aria-label={t('dashboard.share')}
            onClick={onOpenShare}
            className="rounded-full!"
          />
        </Tooltip>
      )}

      {!shareMode && !editing && onOpenSubscriptions && (
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

      {!shareMode && editing && (
        <>
          <PermissionWrapper requiredPermissions={['EditChart']}>
            <Tooltip title={t('dashboard.configUnifiedFilterFields')}>
              <Button
                type="text"
                icon={<SettingOutlined className="text-base" aria-hidden="true" />}
                aria-label={t('dashboard.configUnifiedFilterFields')}
                onClick={onOpenFilterConfig}
                className="rounded-full!"
              />
            </Tooltip>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['EditChart']}>
            <Button
              type="default"
              icon={<PlusOutlined aria-hidden="true" />}
              onClick={onOpenAddComponent}
              className="rounded-full!"
              style={{
                borderColor: chartTheme.panelBorderColor,
                color: 'var(--color-text-1)',
                background: chartTheme.panelBg,
              }}
            >
              {t('opsAnalysis.report.addComponent')}
            </Button>
          </PermissionWrapper>
        </>
      )}

      {!shareMode && (
        <PermissionWrapper requiredPermissions={['EditChart']}>
          {!editing ? (
            <Tooltip title={t('common.edit')}>
              <Button
                type="text"
                aria-label={t('common.edit')}
                icon={<EditOutlined aria-hidden="true" className="text-base" />}
                disabled={!canEnterEdit}
                onClick={onToggleEditMode}
                className="rounded-full!"
              />
            </Tooltip>
          ) : (
            <div className="flex items-center gap-2 ml-4">
              {editExtra}
              <Button
                disabled={!selectedReport?.data_id}
                onClick={onCancelEdit}
                className="rounded-full!"
              >
                {t('common.cancel')}
              </Button>
              <Button
                type="primary"
                loading={saving}
                disabled={!selectedReport?.data_id}
                onClick={onSave}
                className="rounded-full!"
              >
                {t('common.save')}
              </Button>
            </div>
          )}
        </PermissionWrapper>
      )}
    </div>
  );
};

export default ReportToolbar;
