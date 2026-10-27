import React from 'react';
import { useTranslation } from '@/utils/i18n';
import {
  extractComparableValue,
  formatPeriodCompare,
  toComparableNumber,
} from '@/app/ops-analysis/utils/compareQuery';

const TONE_COLOR = {
  up: 'var(--color-fail)',
  down: 'var(--color-success)',
  flat: 'var(--color-text-3)',
};

interface GaugePeriodCompareProps {
  config?: {
    compare?: boolean;
    compareMode?: 'percent' | 'value';
    selectedFields?: string[];
    decimalPlaces?: number;
    unit?: string;
  };
  rawData: unknown;
  baselineData?: unknown;
}

const GaugePeriodCompare: React.FC<GaugePeriodCompareProps> = ({
  config,
  rawData,
  baselineData,
}) => {
  const { t } = useTranslation();
  if (!config?.compare) {
    return null;
  }
  const selectedField = config.selectedFields?.[0];
  const current = toComparableNumber(extractComparableValue(rawData, selectedField));
  const baseline = toComparableNumber(extractComparableValue(baselineData, selectedField));
  const compared = formatPeriodCompare({
    current,
    baseline,
    compareMode: config.compareMode,
    decimalPlaces: config.decimalPlaces,
    unitLabel: config.unit,
  });

  return (
    <div
      data-testid="gauge-compare"
      className="pointer-events-none absolute inset-x-0 bottom-1 z-10 flex items-center justify-center gap-1 overflow-hidden"
    >
      <span className="min-w-0 truncate text-(--color-text-3)" style={{ fontSize: 12 }}>
        {t('dashboard.comparePreviousShortLabel')}
      </span>
      <span className="shrink-0 font-semibold" style={{ color: TONE_COLOR[compared.tone], fontSize: 12 }}>
        {compared.text}
      </span>
    </div>
  );
};

export default GaugePeriodCompare;
