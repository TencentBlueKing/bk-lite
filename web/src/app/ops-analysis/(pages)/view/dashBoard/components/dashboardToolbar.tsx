import React from 'react';
import { Button, Tooltip } from 'antd';
import {
  DownloadOutlined,
  EditOutlined,
  FullscreenOutlined,
  PlusOutlined,
  ReloadOutlined,
  ShareAltOutlined,
  SettingOutlined,
} from '@ant-design/icons';

import type { DirItem } from '@/app/ops-analysis/types';
import PermissionWrapper from '@/components/permission';
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
  onToggleFullscreen: () => void;
  onExportPdf: () => void;
  onOpenFilterConfig: () => void;
  onOpenAddView: () => void;
  onOpenAddGroup: () => void;
  onToggleEditMode: () => void;
  onCancelEdit: () => void;
  onSave: () => void;
  shareMode?: boolean;
  onOpenShare?: () => void;
}

const DashboardToolbar: React.FC<DashboardToolbarProps> = ({
  selectedDashboard,
  chartTheme,
  exporting,
  isFullscreen,
  isEditMode,
  saving,
  onRefresh,
  onToggleFullscreen,
  onExportPdf,
  onOpenFilterConfig,
  onOpenAddView,
  onOpenAddGroup,
  onToggleEditMode,
  onCancelEdit,
  onSave,
  shareMode = false,
  onOpenShare,
}) => {
  const { t } = useTranslation();

  return (
    <div className="flex items-center gap-1.5" data-export-hidden="true">
        <Tooltip title={t('common.refresh')}>
          <Button
            type="text"
            icon={<ReloadOutlined style={{ fontSize: 16 }} />}
            onClick={onRefresh}
            className="rounded-full!"
          />
        </Tooltip>

        <Tooltip title={t('common.fullscreen')}>
          <Button
            type="text"
            icon={<FullscreenOutlined style={{ fontSize: 16 }} />}
            aria-pressed={isFullscreen}
            onClick={onToggleFullscreen}
            className="rounded-full!"
          />
        </Tooltip>

        {!shareMode && !isEditMode && (
          <Tooltip title={t('dashboard.exportPdf')}>
            <Button
              type="text"
              icon={<DownloadOutlined style={{ fontSize: 16 }} />}
              loading={exporting}
              onClick={onExportPdf}
              className="rounded-full!"
            />
          </Tooltip>
        )}

        {!shareMode && !isEditMode && onOpenShare && (
          <Tooltip title="分享">
            <Button type="text" icon={<ShareAltOutlined />} onClick={onOpenShare} className="rounded-full!" />
          </Tooltip>
        )}

        {!shareMode && isEditMode && (
          <>
            <PermissionWrapper requiredPermissions={['EditChart']}>
              <Tooltip title={t('dashboard.configUnifiedFilterFields')}>
                <Button
                  type="text"
                  icon={<SettingOutlined style={{ fontSize: 16 }} />}
                  onClick={onOpenFilterConfig}
                  className="rounded-full!"
                />
              </Tooltip>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['EditChart']}>
              <Button
                type="default"
                icon={<PlusOutlined />}
                onClick={onOpenAddView}
                className="rounded-full!"
                style={{
                  borderColor: chartTheme.panelBorderColor,
                  color: 'var(--color-text-1)',
                  background: chartTheme.panelBg,
                }}
              >
                {t('dashboard.addView')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['EditChart']}>
              <Button
                type="default"
                icon={<PlusOutlined />}
                onClick={onOpenAddGroup}
                className="rounded-full!"
                style={{
                  borderColor: chartTheme.panelBorderColor,
                  color: 'var(--color-text-1)',
                  background: chartTheme.panelBg,
                }}
              >
                {t('dashboard.addGroup')}
              </Button>
            </PermissionWrapper>
          </>
        )}

        {!shareMode && <PermissionWrapper requiredPermissions={['EditChart']}>
          {!isEditMode ? (
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
          ) : (
            <div className="flex items-center gap-2 ml-4">
              <Button
                disabled={!selectedDashboard?.data_id}
                onClick={onCancelEdit}
                className="rounded-full!"
              >
                {t('common.cancel')}
              </Button>
              <Button
                type="primary"
                loading={saving}
                disabled={!selectedDashboard?.data_id}
                onClick={onSave}
                className="rounded-full!"
              >
                {t('common.save')}
              </Button>
            </div>
          )}
        </PermissionWrapper>}
    </div>
  );
};

export default DashboardToolbar;
