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
} from '@ant-design/icons';

const TopologyToolbar: React.FC<ToolbarProps> = ({
  isSelectMode,
  isEditMode = false,
  isFullscreen = false,
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
  onCancel,
  onFilterConfig,
}) => {
  const { t } = useTranslation();
  const iconButtonClassName =
    'rounded-full! h-8 w-8 min-w-8 flex items-center justify-center';

  return (
    <div className="flex items-center gap-1.5">
        <div className="flex items-center gap-0.5">
          <Tooltip title={t('topology.zoomIn')}>
            <Button
              type="text"
              icon={<ZoomInOutlined style={{ fontSize: 16 }} />}
              onClick={onZoomIn}
              className={iconButtonClassName}
            />
          </Tooltip>
          <Tooltip title={t('topology.zoomOut')}>
            <Button
              type="text"
              icon={<ZoomOutOutlined style={{ fontSize: 16 }} />}
              onClick={onZoomOut}
              className={iconButtonClassName}
            />
          </Tooltip>
          <Tooltip title={t('topology.fitView')}>
            <Button
              type="text"
              icon={<PlusSquareOutlined style={{ fontSize: 16 }} />}
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
                  <FullscreenExitOutlined style={{ fontSize: 16 }} />
                ) : (
                  <FullscreenOutlined style={{ fontSize: 16 }} />
                )
              }
              onClick={onFullscreenToggle}
              className={iconButtonClassName}
            />
          </Tooltip>
        </div>

        {isEditMode && (
          <div className="ml-0.5 flex items-center gap-0.5">
            <Tooltip title={t('topology.undo')}>
              <Button
                type="text"
                icon={<UndoOutlined style={{ fontSize: 16 }} />}
                onClick={onUndo}
                disabled={!canUndo}
                className={iconButtonClassName}
              />
            </Tooltip>
            <Tooltip title={t('topology.redo')}>
              <Button
                type="text"
                icon={<RedoOutlined style={{ fontSize: 16 }} />}
                onClick={onRedo}
                disabled={!canRedo}
                className={iconButtonClassName}
              />
            </Tooltip>
            <Tooltip title={t('topology.selectMode')}>
              <Button
                type="text"
                icon={<SelectOutlined style={{ fontSize: 16 }} />}
                onClick={onSelectMode}
                className={iconButtonClassName}
                style={{
                  backgroundColor: isSelectMode ? '#1677ff15' : 'transparent',
                  color: isSelectMode ? '#1677ff' : undefined,
                  borderRadius: 999,
                }}
              />
            </Tooltip>
            <Tooltip title={t('topology.deleteSelected')}>
              <Button
                type="text"
                aria-label={t('topology.deleteSelected')}
                icon={
                  <DeleteOutlined aria-hidden="true" style={{ fontSize: 16 }} />
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
                        style={{ fontSize: 16 }}
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
            onRefresh={onRefresh}
            onFrequenceChange={onFrequencyChange}
          />
        )}

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
                  icon={<EditOutlined style={{ fontSize: 16 }} />}
                  onClick={onEdit}
                  disabled={selectedTopology?.is_build_in}
                  className="rounded-full!"
                />
              </Tooltip>
            )}
          </PermissionWrapper>
        </div>
    </div>
  );
};

export default TopologyToolbar;
