import React from 'react';
import { Button, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ToolbarProps } from '@/app/ops-analysis/types/topology';
import TimeSelector from '@/components/time-selector';
import {
  ZoomInOutlined,
  ZoomOutOutlined,
  FullscreenOutlined,
  DeleteOutlined,
  SelectOutlined,
  EditOutlined,
  UndoOutlined,
  RedoOutlined,
} from '@ant-design/icons';

const TopologyToolbar: React.FC<ToolbarProps> = ({
  isSelectMode,
  isEditMode = false,
  selectedTopology,
  onZoomIn,
  onZoomOut,
  onEdit,
  onSave,
  onFit,
  onDelete,
  onSelectMode,
  onUndo,
  onRedo,
  canUndo = false,
  canRedo = false,
  onRefresh,
  onFrequencyChange,
}) => {
  const { t } = useTranslation();

  return (
    <div className="w-full mb-2 flex items-center justify-between rounded-lg shadow-sm bg-[var(--color-bg-1)] p-3 border border-[var(--color-border-2)]">
      {/* 左侧：拓扑信息 */}
      <div className="flex-1 mr-8">
        {selectedTopology && (
          <div className="p-1 pt-0">
            <h2 className="text-lg font-semibold mb-1 text-[var(--color-text-1)]">
              {selectedTopology.name}
            </h2>
            <p className="text-sm text-[var(--color-text-2)]">
              {selectedTopology.desc}
            </p>
          </div>
        )}
      </div>

      {/* 右侧：工具栏 */}
      <div className="flex items-center space-x-1 rounded-lg p-2">
        {/* 刷新控件 */}
        {onRefresh && onFrequencyChange && (
          <div className="mr-2">
            <TimeSelector
              onlyRefresh={true}
              onRefresh={onRefresh}
              onFrequenceChange={onFrequencyChange}
            />
          </div>
        )}

        <Tooltip title={t('topology.zoomIn')}>
          <Button
            type="text"
            icon={<ZoomInOutlined style={{ fontSize: 16 }} />}
            onClick={onZoomIn}
          />
        </Tooltip>
        <Tooltip title={t('topology.zoomOut')}>
          <Button
            type="text"
            icon={<ZoomOutOutlined style={{ fontSize: 16 }} />}
            onClick={onZoomOut}
          />
        </Tooltip>
        <Tooltip title={t('topology.fitView')}>
          <Button
            type="text"
            icon={<FullscreenOutlined style={{ fontSize: 16 }} />}
            onClick={onFit}
          />
        </Tooltip>

        {isEditMode && (
          <>
            <Tooltip title={t('topology.undo')}>
              <Button
                type="text"
                icon={<UndoOutlined style={{ fontSize: 16 }} />}
                onClick={onUndo}
                disabled={!canUndo}
              />
            </Tooltip>
            <Tooltip title={t('topology.redo')}>
              <Button
                type="text"
                icon={<RedoOutlined style={{ fontSize: 16 }} />}
                onClick={onRedo}
                disabled={!canRedo}
              />
            </Tooltip>
            <Tooltip title={t('topology.selectMode')}>
              <Button
                type="text"
                icon={<SelectOutlined style={{ fontSize: 16 }} />}
                onClick={onSelectMode}
                style={{
                  backgroundColor: isSelectMode ? '#1677ff15' : 'transparent',
                  color: isSelectMode ? '#1677ff' : undefined,
                }}
              />
            </Tooltip>
            <Tooltip title={t('topology.deleteSelected')}>
              <Button
                type="text"
                icon={<DeleteOutlined style={{ fontSize: 16 }} />}
                onClick={onDelete}
              />
            </Tooltip>
          </>
        )}

        <div>
          {isEditMode ? (
            <Button type="primary" onClick={onSave} className="!ml-[20px]">
              {t('common.save')}
            </Button>
          ) : (
            <Tooltip title={t('common.edit')}>
              <Button
                type="text"
                icon={<EditOutlined style={{ fontSize: 16 }} />}
                onClick={onEdit}
              />
            </Tooltip>
          )}
        </div>
      </div>
    </div>
  );
};

export default TopologyToolbar;
