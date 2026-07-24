'use client';

import React from 'react';
import {
  DeleteOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
import type { ScreenWidgetItem } from '@/app/ops-analysis/types/screen';
import { normalizeScreenWidgetAppearance } from '../utils/layout';

interface ScreenWidgetFrameOptions {
  selected?: boolean;
  editMode?: boolean;
  frame?: 'panel' | 'bare';
}

interface ScreenWidgetFrameProps extends ScreenWidgetFrameOptions {
  item: ScreenWidgetItem;
  screenDensity?: number;
  screenUiScale?: number;
  onConfigure?: () => void;
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
  onConfigure,
  onDelete,
  children,
}) => {
  const { t } = useTranslation();
  const frame = normalizeScreenWidgetAppearance(item.valueConfig?.appearance).frame;
  const isBare = frame === 'bare';
  const menuItems: MoreActionsDropdownItem[] = [
    {
      key: 'configure',
      icon: <SettingOutlined />,
      label: t('opsAnalysis.screen.editWidget'),
      onClick: () => onConfigure?.(),
    },
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
        <>
          <div className="screen-widget-frame__corners" aria-hidden="true" />
          <header className="screen-widget-frame__header screen-widget-frame__drag-handle">
            <span className="screen-widget-frame__title">
              {item.title || item.chartType}
            </span>
            <span className="screen-widget-frame__signal" aria-hidden="true" />
          </header>
        </>
      )}
      {isBare && editMode && (
        <>
          <div
            className="screen-widget-frame__bare-header screen-widget-frame__drag-handle"
            aria-hidden="true"
          >
            <span className="screen-widget-frame__title">
              {item.title || item.chartType}
            </span>
          </div>
          <div
            className="screen-widget-frame__drag-surface screen-widget-frame__drag-handle"
            aria-hidden="true"
          />
        </>
      )}
      {editMode && (
        <div className="screen-widget-frame__actions">
          <MoreActionsDropdown
            items={menuItems}
            ariaLabel={t('common.more')}
            stopPropagation
            overlayClassName="screen-widget-frame-actions-menu"
            buttonClassName="screen-widget-frame__action"
          />
        </div>
      )}
      <div className="screen-widget-frame__body">{children}</div>
    </section>
  );
};

export default ScreenWidgetFrame;
