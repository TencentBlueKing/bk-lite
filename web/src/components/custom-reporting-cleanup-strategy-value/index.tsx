import type { ReactNode } from 'react';
import type { CustomReportingCleanupStrategy } from '@/components/custom-reporting-shared/types';
import { useTranslation } from '@/utils/i18n';

export interface CustomReportingCleanupStrategyValueProps {
  strategy?: CustomReportingCleanupStrategy | string | null;
  fallback?: ReactNode;
}

const normalizeStrategy = (
  strategy?: CustomReportingCleanupStrategyValueProps['strategy'],
): CustomReportingCleanupStrategy => {
  if (strategy === 'expire' || strategy === 'snapshot') {
    return strategy;
  }
  return 'none';
};

const CustomReportingCleanupStrategyValue = ({
  strategy,
  fallback,
}: CustomReportingCleanupStrategyValueProps) => {
  const { t } = useTranslation();
  const normalized = normalizeStrategy(strategy);
  const label = t(`CustomReporting.cleanupLabel.${normalized}`);

  return <>{label || fallback || '--'}</>;
};

export default CustomReportingCleanupStrategyValue;
