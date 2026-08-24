'use client';

import { Tooltip } from 'antd';
import {
  deriveHealth,
  HEALTH_DOT_CLASS,
  type HealthLevel,
} from '@/app/apm/components/metric-format';
import type { CatalogStatus } from '@/app/apm/types';
import { useTranslation } from '@/utils/i18n';

interface HealthDotProps {
  level?: HealthLevel;
  status?: CatalogStatus;
  errorRate?: number | null;
  /** 同时展示文案，避免仅靠颜色传达健康状态 */
  showLabel?: boolean;
  className?: string;
}

export default function HealthDot({
  level,
  status,
  errorRate = null,
  showLabel = true,
  className = '',
}: HealthDotProps) {
  const { t } = useTranslation();
  const resolved = level ?? (status ? deriveHealth(status, errorRate) : 5);
  const healthKeys: Record<HealthLevel, string> = {
    1: 'apm.health.critical',
    2: 'apm.health.warning',
    3: 'apm.health.watch',
    4: 'apm.health.good',
    5: 'apm.health.healthy',
  };
  const healthFallback: Record<HealthLevel, string> = {
    1: '严重',
    2: '警告',
    3: '关注',
    4: '良好',
    5: '健康',
  };
  const label = t(healthKeys[resolved], healthFallback[resolved]);
  const dot = (
    <span
      aria-hidden={showLabel ? true : undefined}
      aria-label={showLabel ? undefined : label}
      className={`inline-block h-2 w-2 shrink-0 rounded-full ${HEALTH_DOT_CLASS[resolved]}`}
    />
  );

  if (!showLabel) {
    return (
      <Tooltip title={label}>
        <span className={`inline-flex ${className}`}>{dot}</span>
      </Tooltip>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 ${className}`}
      aria-label={label}
    >
      {dot}
      <span className="text-xs leading-none text-[var(--color-text-3)]">{label}</span>
    </span>
  );
}
