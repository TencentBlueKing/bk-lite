'use client';

import React from 'react';
import { EyeOutlined } from '@ant-design/icons';
import { useScreenAwareRouter } from '@/console-layout';
import { useTranslation } from '@/utils/i18n';
import { SourceItem } from '@/app/alarm/types/integration';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { getHealth, getLogoColor, formatEventCount } from '../utils/health';
import GridEntityCard, {
  type GridEntityCardStatusTone,
} from '@/components/grid-entity-card';

interface IntegrationCardProps {
  src: SourceItem;
}

const HEALTH_TONE: Record<string, GridEntityCardStatusTone> = {
  healthy: 'ok',
  warning: 'warn',
  stale: 'warn',
  silent: 'warn',
  stopped: 'error',
  inactive: 'mute',
};

const IntegrationCard: React.FC<IntegrationCardProps> = ({ src }) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const router = useScreenAwareRouter();
  const health = getHealth(src);
  const logoColor = getLogoColor(src.source_id);
  const monogram = src.name.slice(0, 2).toUpperCase();

  return (
    <GridEntityCard
      name={src.name}
      description={src.description}
      icon={
        src.logo ? (
          <img src={src.logo} alt="" className="h-[22px] w-[22px]" />
        ) : (
          <span className="text-xs font-semibold" style={{ color: logoColor }}>
            {monogram}
          </span>
        )
      }
      statusTone={HEALTH_TONE[health.key]}
      statusLabel={t(health.labelKey)}
      body={
        <div className="flex flex-col gap-1.5 text-[13px] text-[var(--color-text-2)]">
          <div className="flex items-center">
            <span className="w-[100px] shrink-0 text-[var(--color-text-3)]">
              {t('integration.eventCount')}
            </span>
            <span className="font-semibold tabular-nums">
              {formatEventCount(src.event_count)}
            </span>
          </div>
          <div className="flex items-center">
            <span className="w-[100px] shrink-0 text-[var(--color-text-3)]">
              {t('integration.lastEventTime')}
            </span>
            <span className="tabular-nums">
              {src.last_event_time ? convertToLocalizedTime(src.last_event_time) : '--'}
            </span>
          </div>
        </div>
      }
      footer={
        <button
          type="button"
          className="flex items-center gap-1.5 border-none bg-transparent p-0 text-[13px] font-medium text-[var(--color-primary)]"
          onClick={(event) => {
            event.stopPropagation();
            router.push(`/alarm/integration/detail?sourceItemId=${src.id}`);
          }}
        >
          <EyeOutlined className="text-sm" aria-hidden="true" />
          {t('integration.viewDetail')}
        </button>
      }
    />
  );
};

export default IntegrationCard;
