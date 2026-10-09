'use client';

import React, { useEffect } from 'react';
import { Dropdown } from 'antd';
import {
  CopyOutlined,
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
  UpOutlined,
  VerticalAlignBottomOutlined,
  VerticalAlignTopOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import type { ScreenItem } from '@/app/ops-analysis/types/screen';
import {
  resolveAnalysisCanvasInteraction,
  shouldShowAnalysisWidgetCopyAction,
} from '@/app/ops-analysis/utils/widgetCopy';
import { isScreenWidgetItem } from '../utils/screenItems';
import {
  orderScreenItemsByLayer,
  type ScreenLayerAction,
} from '../utils/screenLayer';

export type ScreenItemMenuKey = 'edit' | 'copy' | 'delete' | ScreenLayerAction;

export interface ScreenItemMenuEntry {
  key: ScreenItemMenuKey;
  labelKey: string;
  danger?: boolean;
  disabled?: boolean;
  dividerBefore?: boolean;
}

const LAYER_LABEL_KEYS: Record<ScreenLayerAction, string> = {
  bringToFront: 'opsAnalysis.screen.bringToFront',
  bringToBack: 'opsAnalysis.screen.bringToBack',
  bringForward: 'opsAnalysis.screen.bringForward',
  sendBackward: 'opsAnalysis.screen.sendBackward',
};

export const buildScreenItemMenu = (
  item: ScreenItem,
  items: ScreenItem[],
  options: { shareMode?: boolean; isBuiltIn?: boolean } = {},
): ScreenItemMenuEntry[] => {
  const ordered = orderScreenItemsByLayer(items);
  const index = ordered.findIndex((entry) => entry.id === item.id);
  const atFront = index <= 0;
  const atBack = index < 0 || index >= ordered.length - 1;
  const interaction = resolveAnalysisCanvasInteraction({
    editMode: true,
    shareMode: options.shareMode,
    isBuiltIn: options.isBuiltIn,
  });
  const showCopy =
    interaction === 'edit' &&
    (!isScreenWidgetItem(item) ||
      shouldShowAnalysisWidgetCopyAction({
        interaction,
        sceneWidgetType: item.valueConfig?.sceneWidgetType,
        chartType: item.chartType,
      }));

  const entries: ScreenItemMenuEntry[] = [];
  if (isScreenWidgetItem(item)) {
    entries.push({ key: 'edit', labelKey: 'common.edit' });
  }
  if (showCopy) {
    entries.push({ key: 'copy', labelKey: 'common.copy' });
  }
  entries.push({ key: 'delete', labelKey: 'common.delete', danger: true });
  (Object.keys(LAYER_LABEL_KEYS) as ScreenLayerAction[]).forEach(
    (key, layerIndex) => {
      const atEdge =
        key === 'bringToFront' || key === 'bringForward' ? atFront : atBack;
      entries.push({
        key,
        labelKey: LAYER_LABEL_KEYS[key],
        disabled: atEdge,
        dividerBefore: layerIndex === 0,
      });
    },
  );
  return entries;
};

const MENU_ICONS: Record<ScreenItemMenuKey, React.ReactNode> = {
  edit: <EditOutlined />,
  copy: <CopyOutlined />,
  delete: <DeleteOutlined />,
  bringToFront: <VerticalAlignTopOutlined />,
  bringToBack: <VerticalAlignBottomOutlined />,
  bringForward: <UpOutlined />,
  sendBackward: <DownOutlined />,
};

interface ScreenItemContextMenuProps {
  open: boolean;
  x: number;
  y: number;
  entries: ScreenItemMenuEntry[];
  onAction: (key: ScreenItemMenuKey) => void;
  onClose: () => void;
}

export const ScreenItemContextMenu: React.FC<ScreenItemContextMenuProps> = ({
  open,
  x,
  y,
  entries,
  onAction,
  onClose,
}) => {
  const { t } = useTranslation();

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest('.ant-dropdown')) return;
      onClose();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [onClose, open]);

  if (!open) return null;

  return (
    <Dropdown
      open
      getPopupContainer={() => document.body}
      overlayStyle={{ zIndex: 1100 }}
      menu={{
        className: 'screen-item-context-menu',
        items: entries.flatMap((entry) => {
          const row = {
            key: entry.key,
            disabled: entry.disabled,
            danger: entry.danger,
            icon: MENU_ICONS[entry.key],
            label: t(entry.labelKey),
          };
          return entry.dividerBefore
            ? [{ type: 'divider' as const }, row]
            : [row];
        }),
        onClick: ({ key }) => onAction(key as ScreenItemMenuKey),
      }}
    >
      <div
        style={{
          position: 'fixed',
          left: x,
          top: y,
          width: 1,
          height: 1,
        }}
      />
    </Dropdown>
  );
};
