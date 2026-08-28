'use client';

import React from 'react';
import {
  CopyOutlined,
  DeleteOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
import type { ScreenWidgetItem } from '@/app/ops-analysis/types/screen';
import { normalizeScreenWidgetAppearance } from '../utils/layoutUtils';
import {
  resolveAnalysisCanvasInteraction,
  shouldShowAnalysisWidgetCopyAction,
} from '@/app/ops-analysis/utils/widgetCopy';

interface ScreenWidgetFrameOptions {
  selected?: boolean;
  editMode?: boolean;
  frame?: 'panel' | 'bare';
}

interface ScreenWidgetFrameProps extends ScreenWidgetFrameOptions {
  item: ScreenWidgetItem;
  screenDensity?: number;
  screenUiScale?: number;
  shareMode?: boolean;
  isBuiltIn?: boolean;
  onConfigure?: () => void;
  onCopy?: () => void;
  onDelete?: () => void;
  children: React.ReactNode;
}

const emphasisClassByType: Record<string, string> = {
  single: 'screen-widget-frame--kpi',
  gauge: 'screen-widget-frame--gauge',
  topN: 'screen-widget-frame--rank',
  eventTable: 'screen-widget-frame--event',
  networkStatusTopology: 'screen-widget-frame--topology',
};

export const getScreenWidgetFrameClassName = (
  item: Pick<ScreenWidgetItem, 'chartType'>,
  options: ScreenWidgetFrameOptions = {},
) => {
  const emphasisClass =
    emphasisClassByType[item.chartType] || 'screen-widget-frame--chart';

  return [
    'screen-widget-frame',
    emphasisClass,
    options.frame === 'bare' ? 'screen-widget-frame--bare' : '',
    options.selected ? 'screen-widget-frame--selected' : '',
    options.editMode ? 'screen-widget-frame--editable' : '',
  ]
    .filter(Boolean)
    .join(' ');
};

const ScreenWidgetFrame: React.FC<ScreenWidgetFrameProps> = ({
  item,
  selected = false,
  editMode = false,
  screenDensity = 1,
  screenUiScale = 1,
  shareMode = false,
  isBuiltIn = false,
  onConfigure,
  onCopy,
  onDelete,
  children,
}) => {
  const { t } = useTranslation();
  const frame = normalizeScreenWidgetAppearance(item.valueConfig?.appearance).frame;
  const isBare = frame === 'bare';
  const showCopy = shouldShowAnalysisWidgetCopyAction({
    interaction: resolveAnalysisCanvasInteraction({
      editMode,
      shareMode,
      isBuiltIn,
    }),
    sceneWidgetType: item.valueConfig?.sceneWidgetType,
    chartType: item.chartType,
  });
  const copyMenuItem: MoreActionsDropdownItem | null = showCopy
    ? {
      key: 'copy',
      icon: <CopyOutlined />,
      label: t('common.copy'),
      onClick: () => onCopy?.(),
    }
    : null;
  const menuItems: MoreActionsDropdownItem[] = [
    {
      key: 'configure',
      icon: <SettingOutlined />,
      label: t('opsAnalysis.screen.editWidget'),
      onClick: () => onConfigure?.(),
    },
    ...(copyMenuItem ? [copyMenuItem] : []),
    {
      key: 'delete',
      danger: true,
      icon: <DeleteOutlined />,
      label: t('opsAnalysis.screen.deleteWidget'),
      onClick: () => onDelete?.(),
    },
  ];

  return (
    <section
      className={getScreenWidgetFrameClassName(item, {
        selected,
        editMode,
        frame,
      })}
      style={{
        '--screen-widget-scale': screenDensity,
        '--screen-widget-ui-scale': screenUiScale,
      } as React.CSSProperties}
    >
      {!isBare && (
        <React.Fragment key="decoration">
          <div className="screen-widget-frame__corners" aria-hidden="true" />
          <header className="screen-widget-frame__header screen-widget-frame__drag-handle">
            <span className="screen-widget-frame__title">
              {item.title || item.chartType}
            </span>
            <span className="screen-widget-frame__signal" aria-hidden="true" />
          </header>
        </React.Fragment>
      )}
      {isBare && editMode && (
        <div
          key="drag-surface"
          className="screen-widget-frame__drag-surface screen-widget-frame__drag-handle"
          aria-hidden="true"
        />
      )}
      {editMode && (
        <div key="actions" className="screen-widget-frame__actions">
          <MoreActionsDropdown
            items={menuItems}
            ariaLabel={t('common.more')}
            stopPropagation
            overlayClassName="screen-widget-frame-actions-menu"
            buttonClassName="screen-widget-frame__action"
          />
        </div>
      )}
      <div key="body" className="screen-widget-frame__body">{children}</div>
    </section>
  );
};

export default ScreenWidgetFrame;
