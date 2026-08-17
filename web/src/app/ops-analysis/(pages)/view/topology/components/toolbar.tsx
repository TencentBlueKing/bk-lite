import React from 'react';
import { Button, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ToolbarProps } from '@/app/ops-analysis/types/topology';
import TimeSelector from '@/components/time-selector';
import PermissionWrapper from '@/components/permission';
import {
  ZoomInOutlined,
  ZoomOutOutlined,
  PlusSquareOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  DeleteOutlined,
  SelectOutlined,
  EditOutlined,
  UndoOutlined,
  RedoOutlined,
  SettingOutlined,
  ShareAltOutlined,
} from '@ant-design/icons';

const TopologyToolbar: React.FC<ToolbarProps> = ({
  isSelectMode,
  isEditMode = false,
  isFullscreen = false,
  shareMode = false,
  shareLoading = false,
  onOpenShare,
  selectedTopology,
  onZoomIn,
  onZoomOut,
  onEdit,
  onSave,
  onFullscreenToggle,
  onFit,
  onDelete,
  onSelectMode,
  onUndo,
  onRedo,
  canUndo = false,
  canRedo = false,
  onRefresh,
  onFrequencyChange,
  frequenceValue = 0,
  onCancel,
  onFilterConfig,
}) => {
  const { t } = useTranslation();
  const iconButtonClassName =
    'rounded-full! h-8 w-8 min-w-8 flex items-center justify-center';
  const iconClassName = 'text-[16px]';

  return (
    <div className="flex items-center gap-1.5">
        <div className="flex items-center gap-0.5">
          <Tooltip title={t('topology.zoomIn')}>
            <Button
              type="text"
              icon={<ZoomInOutlined className={iconClassName} />}
              onClick={onZoomIn}
              className={iconButtonClassName}
            />
          </Tooltip>
          <Tooltip title={t('topology.zoomOut')}>
            <Button
              type="text"
              icon={<ZoomOutOutlined className={iconClassName} />}
              onClick={onZoomOut}
              className={iconButtonClassName}
            />
          </Tooltip>
          <Tooltip title={t('topology.fitView')}>
            <Button
              type="text"
              icon={<PlusSquareOutlined className={iconClassName} />}
              onClick={onFit}
              className={iconButtonClassName}
            />
          </Tooltip>
          <Tooltip
            title={
              isFullscreen ? t('common.exitFullscreen') : t('common.fullscreen')
            }
          >
            <Button
              type="text"
              icon={
                isFullscreen ? (
                  <FullscreenExitOutlined className={iconClassName} />
                ) : (
                  <FullscreenOutlined className={iconClassName} />
                )
              }
              onClick={onFullscreenToggle}
              className={iconButtonClassName}
            />
          </Tooltip>
        </div>

        {!shareMode && isEditMode && (
          <div className="ml-0.5 flex items-center gap-0.5">
            <Tooltip title={t('topology.undo')}>
              <Button
                type="text"
                icon={<UndoOutlined className={iconClassName} />}
                onClick={onUndo}
                disabled={!canUndo}
                className={iconButtonClassName}
              />
            </Tooltip>
            <Tooltip title={t('topology.redo')}>
              <Button
                type="text"
                icon={<RedoOutlined className={iconClassName} />}
                onClick={onRedo}
                disabled={!canRedo}
                className={iconButtonClassName}
              />
            </Tooltip>
            <Tooltip title={t('topology.selectMode')}>
              <Button
                type="text"
                icon={<SelectOutlined className={iconClassName} />}
                onClick={onSelectMode}
                className={iconButtonClassName}
                style={{
                  backgroundColor: isSelectMode ? '#1677ff15' : 'transparent',
                  color: isSelectMode ? '#1677ff' : undefined,
                }}
              />
            </Tooltip>
            <Tooltip title={t('topology.deleteSelected')}>
              <Button
                type="text"
                aria-label={t('topology.deleteSelected')}
                icon={
                  <DeleteOutlined aria-hidden="true" className={iconClassName} />
                }
                onClick={onDelete}
                className={iconButtonClassName}
              />
            </Tooltip>
            {onFilterConfig && (
              <PermissionWrapper requiredPermissions={['EditChart']}>
                <Tooltip title={t('dashboard.configUnifiedFilterFields')}>
                  <Button
                    type="text"
                    aria-label={t('dashboard.configUnifiedFilterFields')}
                    icon={
                      <SettingOutlined
                        aria-hidden="true"
                        className={iconClassName}
                      />
                    }
                    onClick={onFilterConfig}
                    className={iconButtonClassName}
                  />
                </Tooltip>
              </PermissionWrapper>
            )}
          </div>
        )}

        {/* 刷新控件 */}
        {onRefresh && onFrequencyChange && (
          <TimeSelector
            onlyRefresh={true}
            frequenceValue={frequenceValue}
            onRefresh={onRefresh}
            onFrequenceChange={onFrequencyChange}
          />
        )}

        {!shareMode && !isEditMode && onOpenShare && (
          <Tooltip title={t('dashboard.share')}>
            <Button
              type="text"
              icon={<ShareAltOutlined className={iconClassName} />}
              loading={shareLoading}
              disabled={shareLoading}
              aria-label={t('dashboard.share')}
              onClick={onOpenShare}
              className={iconButtonClassName}
            />
          </Tooltip>
        )}

        {!shareMode && (
          <div>
            <PermissionWrapper requiredPermissions={['EditChart']}>
              {isEditMode ? (
                <div className="flex items-center gap-2 ml-2">
                  {onCancel && (
                    <Button onClick={onCancel} className="rounded-full!">
                      {t('common.cancel')}
                    </Button>
                  )}
                  <Button
                    type="primary"
                    onClick={onSave}
                    className="rounded-full!"
                  >
                    {t('common.save')}
                  </Button>
                </div>
              ) : (
                <Tooltip title={t('common.edit')}>
                  <Button
                    type="text"
                    icon={<EditOutlined className={iconClassName} />}
                    onClick={onEdit}
                    disabled={selectedTopology?.is_build_in}
                    className="rounded-full!"
                  />
                </Tooltip>
              )}
            </PermissionWrapper>
          </div>
        )}
    </div>
  );
};

export default TopologyToolbar;
