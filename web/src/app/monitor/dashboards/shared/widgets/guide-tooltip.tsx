'use client';

import React from 'react';
import { Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import { GuideItem } from '../types';
import { localizeGuideItems, tDashboardText, useDashboardText } from '../utils/content-i18n';

export interface GuideTooltipStyles {
  metricGuideTooltip?: string;
  metricGuideTooltipRow?: string;
  titleWithGuide?: string;
  metricGuideIcon?: string;
}

export const GuideTooltipContent = ({
  items,
  styles
}: {
  items: GuideItem[];
  styles: GuideTooltipStyles;
}) => {
  const { t } = useDashboardText();
  const localized = localizeGuideItems(t, items);
  return (
  <div className={styles.metricGuideTooltip}>
    {localized.map((item) => (
      <div key={item.label} className={styles.metricGuideTooltipRow}>
        <strong>{item.label}</strong>
        <span>{item.detail}</span>
      </div>
    ))}
  </div>
  );
};

export const TitleWithGuide = ({
  title,
  items,
  className,
  styles
}: {
  title: React.ReactNode;
  items: GuideItem[];
  className?: string;
  styles: GuideTooltipStyles;
}) => {
  const { t } = useDashboardText();
  const hasGuideItems = items.length > 0;
  const localizedTitle = typeof title === 'string' ? tDashboardText(t, title) : title;

  return (
    <span className={[styles.titleWithGuide, className].filter(Boolean).join(' ')}>
      <span>{localizedTitle}</span>
      {hasGuideItems ? (
        <Tooltip overlayClassName="lightMetricTooltip" title={<GuideTooltipContent items={items} styles={styles} />}>
          <InfoCircleOutlined className={styles.metricGuideIcon} />
        </Tooltip>
      ) : null}
    </span>
  );
};
