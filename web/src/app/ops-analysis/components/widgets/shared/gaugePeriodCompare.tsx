import React from 'react';
import { useTranslation } from '@/utils/i18n';
import {
  extractComparableValue,
  formatPeriodCompare,
  toComparableNumber,
} from '@/app/ops-analysis/utils/compareQuery';
import {
  readScalarCalc,
  reduceScalarRecords,
  type ScalarCalcConfig,
} from '@/app/ops-analysis/utils/scalarReduction';

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
    scalarCalc?: ScalarCalcConfig;
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
  const scalarCalc = readScalarCalc(config.scalarCalc);
  const currentReduction = scalarCalc ? reduceScalarRecords(rawData, scalarCalc) : null;
  const current = currentReduction
    ? (currentReduction.status === 'value' ? currentReduction.value : null)
    : toComparableNumber(extractComparableValue(rawData, selectedField));
  const baselineReduction = scalarCalc ? reduceScalarRecords(baselineData, scalarCalc) : null;
  const baseline = baselineReduction
    ? (baselineReduction.status === 'value' ? baselineReduction.value : null)
    : toComparableNumber(extractComparableValue(baselineData, selectedField));
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
