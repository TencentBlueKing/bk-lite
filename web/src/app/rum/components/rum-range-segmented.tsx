'use client';

import { Segmented } from 'antd';

import type { RumAnalyticsRange } from '@/app/rum/lib/degradation';
import { useTranslation } from '@/utils/i18n';

export const RUM_ANALYTICS_RANGES: RumAnalyticsRange[] = ['1h', '24h', '7d'];

/** RUM 分析时间窗：短标签 Segmented，与 APM 时间窗同形态。 */
export default function RumRangeSegmented({
  value,
  onChange,
  className,
  block,
  size = 'middle',
}: {
  value: RumAnalyticsRange;
  onChange: (value: RumAnalyticsRange) => void;
  className?: string;
  block?: boolean;
  size?: 'small' | 'middle' | 'large';
}) {
  const { t } = useTranslation();
  return (
    <Segmented
      aria-label={t('rum.common.timeWindow', '时间窗')}
      className={className}
      block={block}
      size={size}
      value={value}
      options={RUM_ANALYTICS_RANGES}
      onChange={(next) => onChange(next as RumAnalyticsRange)}
    />
  );
}
