'use client';

import React from 'react';
import type { ScreenWidgetItem } from '@/app/ops-analysis/types/screen';
import type { ScreenWidgetFrame } from '@/app/ops-analysis/types/dashBoard';
import { resolveScreenWidgetAppearance } from '../utils/layoutUtils';

interface ScreenWidgetFrameOptions {
  selected?: boolean;
  editMode?: boolean;
  frame?: ScreenWidgetFrame;
}

interface ScreenWidgetFrameProps extends ScreenWidgetFrameOptions {
  item: ScreenWidgetItem;
  screenDensity?: number;
  screenUiScale?: number;
  children: React.ReactNode;
}

const emphasisClassByType: Record<string, string> = {
  single: 'screen-widget-frame--kpi',
  gauge: 'screen-widget-frame--gauge',
  topN: 'screen-widget-frame--rank',
  eventTable: 'screen-widget-frame--event',
  networkStatusTopology: 'screen-widget-frame--topology',
  relatedTopology: 'screen-widget-frame--topology',
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
  children,
}) => {
  const appearance = resolveScreenWidgetAppearance(
    item.chartType,
    item.valueConfig?.appearance,
  );
  const frame = appearance.frame;
  const isBare = frame === 'bare';

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
        <header
          key="header"
          className="screen-widget-frame__header screen-widget-frame__drag-handle"
        >
          <span className="screen-widget-frame__title">
            {item.title || item.chartType}
          </span>
        </header>
      )}
      {isBare && editMode && (
        <div
          key="drag-surface"
          className="screen-widget-frame__drag-surface screen-widget-frame__drag-handle"
          aria-hidden="true"
        />
      )}
      <div key="body" className="screen-widget-frame__body">{children}</div>
    </section>
  );
};

export default ScreenWidgetFrame;
