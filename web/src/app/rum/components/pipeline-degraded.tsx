'use client';

import { Alert } from 'antd';

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
      ? t('rum.pipeline.controlUnavailable', 'RUM 控制面暂不可用，应用目录可能为空。')
      : t('rum.pipeline.analyticsUnavailable', 'RUM 分析数据面暂不可用，指标与列表可能为空。');

  return <Alert type="warning" showIcon message={message} className="mb-3" />;
}
