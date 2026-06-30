'use client';

import React from 'react';
import { Dropdown, type MenuProps } from 'antd';
import {
  DeleteOutlined,
  MoreOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import type { ScreenWidgetItem } from '@/app/ops-analysis/types/screen';

interface ScreenWidgetFrameOptions {
  selected?: boolean;
  editMode?: boolean;
}

interface ScreenWidgetFrameProps extends ScreenWidgetFrameOptions {
  item: ScreenWidgetItem;
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
  onConfigure,
  onDelete,
  children,
}) => {
  const { t } = useTranslation();
  const menuItems: MenuProps['items'] = [
    {
      key: 'configure',
      icon: <SettingOutlined />,
      label: t('opsAnalysis.screen.editWidget'),
      onClick: ({ domEvent }) => {
        domEvent.stopPropagation();
        onConfigure?.();
      },
    },
    {
      key: 'delete',
      danger: true,
      icon: <DeleteOutlined />,
      label: t('opsAnalysis.screen.deleteWidget'),
      onClick: ({ domEvent }) => {
        domEvent.stopPropagation();
        onDelete?.();
      },
    },
  ];

  return (
    <section
      className={getScreenWidgetFrameClassName(item, { selected, editMode })}
    >
      <div className="screen-widget-frame__corners" aria-hidden="true" />
      <header className="screen-widget-frame__header">
        <span className="screen-widget-frame__title">
          {item.title || item.chartType}
        </span>
        <span className="screen-widget-frame__signal" aria-hidden="true" />
      </header>
      {editMode && (
        <div className="screen-widget-frame__actions">
          <Dropdown menu={{ items: menuItems }} trigger={['click']}>
            <button
              type="button"
              className="screen-widget-frame__action"
              aria-label="更多操作"
              title="更多操作"
              onClick={(event) => {
                event.stopPropagation();
              }}
            >
              <MoreOutlined aria-hidden="true" />
            </button>
          </Dropdown>
        </div>
      )}
      <div className="screen-widget-frame__body">{children}</div>
    </section>
  );
};

export default ScreenWidgetFrame;
