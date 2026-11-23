'use client';

import { Alert, Empty } from 'antd';

import { useTranslation } from '@/utils/i18n';

/** Soft banner when control plane or Victoria analytics is unavailable. */
export default function PipelineDegradedBanner({
  reason,
}: {
  reason: 'control' | 'analytics';
}) {
  const { t } = useTranslation();
  const message =
    reason === 'control'
      ? t('rum.pipeline.controlUnavailable', 'RUM 控制面暂不可用，无法确认接入状态。')
      : t('rum.pipeline.analyticsUnavailable', 'RUM 分析数据面暂不可用，指标与列表可能为空。');

  return <Alert type="warning" showIcon message={message} className="mb-3" />;
}

/** Empty list while a pipeline is down. A real empty sample uses the page's own copy. */
export function RumDegradedEmpty({ reason }: { reason: 'control' | 'analytics' }) {
  const { t } = useTranslation();
  return (
    <Empty
      description={
        reason === 'control'
          ? t('rum.pipeline.emptyControl', '无法确认接入状态，列表暂时为空。')
          : t('rum.pipeline.emptyAnalytics', '分析数据面暂不可用，列表暂时为空。')
      }
    />
  );
}
