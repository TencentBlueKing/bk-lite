import React from 'react';
import { Button, Tooltip } from 'antd';
import {
  ZoomInOutlined,
  ZoomOutOutlined,
  PlusSquareOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  EditOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import TimeSelector from '@/components/time-selector';

export interface NetworkToolbarProps {
  editMode: boolean;
  dirty: boolean;
  saving: boolean;
  /** 节点缩放 / 自适应。 */
  onZoomIn?: () => void;
  onZoomOut?: () => void;
  onFit?: () => void;
  isFullscreen?: boolean;
  onFullscreenToggle?: () => void;
  /** 运行态刷新(对应 reference 的 TimeSelector.refresh)。 */
  onRefresh: () => void;
  onFrequencyChange: (intervalMs: number) => void;
  /** 编辑 / 取消 / 保存。 */
  onEnterEdit: () => void;
  onCancelEdit: () => void;
  onSave: () => void;
}

/**
 * 网络拓扑工具栏(design.md §7.6)。
 *
 * 形态对齐 reference `topology/components/toolbar.tsx`:
 * - `flex items-center gap-1.5` 极简布局
 * - 左:zoom / fit / fullscreen(读 / 写共用)
 * - 中:刷新(对应 reference 的 TimeSelector 仅刷新模式)
 * - 右:只读 → 编辑;编辑 → 取消 + 保存
 *
 * P0 范围(对照 spec §2.2):
 * - 不提供 undo/redo(节点位置保存即生效,无需撤销栈)
 * - 不提供 selectMode(画布默认即可选中)
 * - 不提供 setting / filterConfig(无 filter 概念)
 * - 不提供节点 / 链路级删除按钮(由 Drawer 提供)
 * - 不提供状态计数(节点 / 链路状态展示由节点外层颜色和连线颜色表达,见 spec §5/§6)
 */
const NetworkToolbar: React.FC<NetworkToolbarProps> = ({
  editMode,
  dirty,
  saving,
  onZoomIn,
  onZoomOut,
  onFit,
  isFullscreen,
  onFullscreenToggle,
  onRefresh,
  onFrequencyChange,
  onEnterEdit,
  onCancelEdit,
  onSave,
}) => {
  const { t } = useTranslation();
  const iconButtonClassName =
    'rounded-full! h-8 w-8 min-w-8 flex items-center justify-center';

  return (
    <div className="flex items-center gap-1.5" data-testid="network-toolbar">
      <div className="flex items-center gap-0.5">
        {onZoomIn && (
          <Tooltip title={t('opsAnalysis.networkTopology.toolbar.zoomIn')}>
            <Button
              type="text"
              icon={<ZoomInOutlined style={{ fontSize: 16 }} />}
              onClick={onZoomIn}
              className={iconButtonClassName}
            />
          </Tooltip>
        )}
        {onZoomOut && (
          <Tooltip title={t('opsAnalysis.networkTopology.toolbar.zoomOut')}>
            <Button
              type="text"
              icon={<ZoomOutOutlined style={{ fontSize: 16 }} />}
              onClick={onZoomOut}
              className={iconButtonClassName}
            />
          </Tooltip>
        )}
        {onFit && (
          <Tooltip title={t('opsAnalysis.networkTopology.toolbar.fit')}>
            <Button
              type="text"
              icon={<PlusSquareOutlined style={{ fontSize: 16 }} />}
              onClick={onFit}
              className={iconButtonClassName}
            />
          </Tooltip>
        )}
        {onFullscreenToggle && (
          <Tooltip
            title={t(
              isFullscreen
                ? 'opsAnalysis.networkTopology.toolbar.exitFullscreen'
                : 'opsAnalysis.networkTopology.toolbar.fullscreen',
            )}
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
        )}
      </div>

      <TimeSelector
        onlyRefresh
        onRefresh={onRefresh}
        onFrequenceChange={onFrequencyChange}
        className="network-topology-refresh"
      />

      <div className="ml-2">
        {editMode ? (
          <div className="flex items-center gap-2">
            <Button
              onClick={onCancelEdit}
              className="rounded-full!"
              data-testid="network-toolbar-cancel-edit"
            >
              {t('opsAnalysis.networkTopology.actions.cancel')}
            </Button>
            <Button
              type="primary"
              onClick={onSave}
              loading={saving}
              disabled={!dirty}
              className="rounded-full!"
              data-testid="network-toolbar-save"
            >
              {t('opsAnalysis.networkTopology.actions.save')}
            </Button>
          </div>
        ) : (
          <Tooltip title={t('opsAnalysis.networkTopology.toolbar.edit')}>
            <Button
              type="text"
              icon={<EditOutlined style={{ fontSize: 16 }} />}
              onClick={onEnterEdit}
              className="rounded-full!"
              data-testid="network-toolbar-enter-edit"
            />
          </Tooltip>
        )}
      </div>
    </div>
  );
};

export default NetworkToolbar;
