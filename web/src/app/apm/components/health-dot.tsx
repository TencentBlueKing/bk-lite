import { Tooltip } from 'antd';
import { deriveHealth, HEALTH_DOT_CLASS, HEALTH_LABEL, type HealthLevel } from '@/app/apm/components/metric-format';
import type { CatalogStatus } from '@/app/apm/types';

interface HealthDotProps {
  level?: HealthLevel;
  status?: CatalogStatus;
  errorRate?: number | null;
  className?: string;
}

export default function HealthDot({ level, status, errorRate = null, className = '' }: HealthDotProps) {
  const resolved = level ?? (status ? deriveHealth(status, errorRate) : 5);
  return (
    <Tooltip title={HEALTH_LABEL[resolved]}>
      <span
        aria-label={HEALTH_LABEL[resolved]}
        className={`inline-block h-2 w-2 shrink-0 rounded-full ${HEALTH_DOT_CLASS[resolved]} ${className}`}
      />
    </Tooltip>
  );
}
