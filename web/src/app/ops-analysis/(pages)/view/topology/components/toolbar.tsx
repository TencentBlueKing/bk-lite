import React from 'react';
import { Button, Tooltip, Tag } from 'antd';
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
  DesktopOutlined,
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
  onPresentationConfig,
}) => {
  const { t } = useTranslation();
  const iconButtonClassName =
    'rounded-full! h-8 w-8 min-w-8 flex items-center justify-center';

  return (
    <div
      className="w-full mb-2.5 flex items-center justify-between rounded-xl bg-(--color-bg-1) px-3.5 py-2.5 border border-(--color-border-2)"
      style={{ boxShadow: '0 8px 22px rgba(31, 63, 104, 0.05)' }}
    >
      {/* 左侧：拓扑信息 */}
      <div className="flex-1 mr-6">
        {selectedTopology && (
          <div className="pt-0.5">
            <h2 className="text-xl leading-7 font-semibold mb-1 text-(--color-text-1)">
              {selectedTopology.name}
              {selectedTopology.is_build_in && (
                <Tag
                  color="blue"
                  className="ml-2 text-xs align-middle rounded-full! px-2! py-0.5!"
                >
                  {t('common.builtIn')}
                </Tag>
              )}
            </h2>
            <p className="text-sm leading-5 text-(--color-text-2)">
              {selectedTopology.desc}
            </p>
          </div>
        )}
      </div>

      {/* 右侧：工具栏 */}
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
            {onPresentationConfig && (
              <PermissionWrapper requiredPermissions={['EditChart']}>
                <Button
                  type="text"
                  icon={<DesktopOutlined style={{ fontSize: 16 }} />}
                  onClick={onPresentationConfig}
                  className="rounded-full! px-3!"
                >
                  {t('topology.presentationConfig')}
                </Button>
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
    </div>
  );
};

export default TopologyToolbar;
