'use client';

import React from 'react';
import { Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import type { GuideItem } from '@/app/monitor/components/monitor-dashboard-widgets/types';

export interface GuideTooltipStyles {
  metricGuideTooltip?: string;
  metricGuideTooltipRow?: string;
  titleWithGuide?: string;
  metricGuideIcon?: string;
}

const GuideTooltipContent = ({
  items,
  styles,
}: {
  items: GuideItem[];
  styles: GuideTooltipStyles;
}) => (
  <div className={styles.metricGuideTooltip}>
    {items.map((item) => (
      <div key={item.label} className={styles.metricGuideTooltipRow}>
        <strong>{item.label}</strong>
        <span>{item.detail}</span>
      </div>
    ))}
  </div>
);

export const TitleWithGuide = ({
  title,
  items,
  className,
  styles,
}: {
  title: React.ReactNode;
  items: GuideItem[];
  className?: string;
  styles: GuideTooltipStyles;
}) => {
  const hasGuideItems = items.length > 0;

  return (
    <span className={[styles.titleWithGuide, className].filter(Boolean).join(' ')}>
      <span>{title}</span>
      {hasGuideItems ? (
        <Tooltip
          overlayClassName="lightMetricTooltip"
          title={<GuideTooltipContent items={items} styles={styles} />}
        >
          <InfoCircleOutlined className={styles.metricGuideIcon} />
        </Tooltip>
      ) : null}
    </span>
  );
};
