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
  loading = false,
}: {
  value: RumAnalyticsRange;
  onChange: (value: RumAnalyticsRange) => void;
  className?: string;
  block?: boolean;
  size?: 'small' | 'middle' | 'large';
  /** While analytics refetch: disable extra clicks and mark busy for a11y. */
  loading?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <Segmented
      aria-label={t('rum.common.timeWindow', '时间窗')}
      aria-busy={loading || undefined}
      className={className}
      block={block}
      size={size}
      value={value}
      disabled={loading}
      options={RUM_ANALYTICS_RANGES}
      onChange={(next) => onChange(next as RumAnalyticsRange)}
    />
  );
}
