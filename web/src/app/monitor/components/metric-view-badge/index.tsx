'use client';

import { Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';

export interface MetricViewConfig {
  mode: 'top' | 'bottom' | 'limited';
  limit?: number;
}

const MetricViewBadge = ({ config }: { config?: MetricViewConfig }) => {
  const { t } = useTranslation();

  if (!config) return null;

  const labelKey = {
    top: 'monitor.views.controlledViewTop',
    bottom: 'monitor.views.controlledViewBottom',
    limited: 'monitor.views.controlledViewLimited'
  }[config.mode];
  const mode =
    config.mode === 'bottom'
      ? t('monitor.views.controlledViewModeBottom')
      : t('monitor.views.controlledViewModeTop');
  const limit = config.limit ?? '';

  return (
    <Tooltip
      placement="top"
      title={t('monitor.views.controlledViewHint', '', { mode, limit })}
    >
      <span className="ml-[8px] shrink-0 text-[12px] text-[var(--color-primary)] cursor-default whitespace-nowrap">
        {t(labelKey, '', { limit })}
      </span>
    </Tooltip>
  );
};

export default MetricViewBadge;
