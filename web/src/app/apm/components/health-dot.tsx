import { Tooltip } from 'antd';
import {
  deriveHealth,
  HEALTH_DOT_CLASS,
  HEALTH_LABEL,
  type HealthLevel,
} from '@/app/apm/components/metric-format';
import type { CatalogStatus } from '@/app/apm/types';

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
  showLabel = false,
  className = '',
}: HealthDotProps) {
  const resolved = level ?? (status ? deriveHealth(status, errorRate) : 5);
  const label = HEALTH_LABEL[resolved];
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
      title={label}
    >
      {dot}
      <span className="text-[11px] leading-none text-[var(--color-text-3)]">{label}</span>
    </span>
  );
}
