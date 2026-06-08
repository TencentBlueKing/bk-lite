import React from 'react';
import { Button, Tag, Tooltip } from 'antd';
import {
  DownloadOutlined,
  EditOutlined,
  FullscreenOutlined,
  PlusOutlined,
  ReloadOutlined,
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
}) => {
  const { t } = useTranslation();

  return (
    <div className="w-full mb-2 flex items-center justify-between bg-(--color-bg-1) px-4 py-2 border-b border-(--color-border-2)">
      <div className="flex-1 mr-8">
        {selectedDashboard && (
          <div>
            <h2 className="text-base leading-6 font-semibold text-(--color-text-1)">
              {selectedDashboard.name}
              {selectedDashboard.is_build_in && (
                <Tag
                  color="blue"
                  className="ml-2 text-xs align-middle rounded-full! px-2! py-0.5!"
                >
                  {t('common.builtIn')}
                </Tag>
              )}
            </h2>
            {selectedDashboard.desc && (
              <p className="text-xs leading-4 text-(--color-text-3) mt-0.5">
                {selectedDashboard.desc}
              </p>
            )}
          </div>
        )}
      </div>

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

        {!isEditMode && (
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

        {isEditMode && (
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

        <PermissionWrapper requiredPermissions={['EditChart']}>
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
        </PermissionWrapper>
      </div>
    </div>
  );
};

export default DashboardToolbar;
