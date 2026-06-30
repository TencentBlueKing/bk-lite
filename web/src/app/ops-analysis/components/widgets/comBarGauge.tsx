import React, { useEffect } from 'react';
import { Empty, Spin } from 'antd';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import {
  formatDisplayValue,
  getColorByThreshold,
} from '@/app/ops-analysis/utils/thresholdUtils';
import {
  extractComparableValue,
  toComparableNumber,
} from '@/app/ops-analysis/utils/compareQuery';
import { applyValueMapping } from '@/app/ops-analysis/utils/valueMapping';

interface ComBarGaugeProps {
  rawData: unknown;
  loading?: boolean;
  config?: ValueConfig;
  onReady?: (ready: boolean) => void;
}

const clamp = (v: number, min: number, max: number) =>
  Math.min(Math.max(v, min), max);

/**
 * Bar gauge（对齐 Grafana）：单指标横向条形量规。
 * 填充宽度 =（值-min）/（max-min），颜色按阈值取，标签经单位库/值映射格式化。
 */
const ComBarGauge: React.FC<ComBarGaugeProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
}) => {
  const selectedField = config?.selectedFields?.[0];
  const numericValue = toComparableNumber(
    extractComparableValue(rawData, selectedField),
  );
  const hasData = numericValue !== null;

  useEffect(() => {
    if (!loading) onReady?.(hasData);
  }, [hasData, loading, onReady]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }
  if (!hasData) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  const min = Number(config?.gaugeMin ?? 0);
  const max = Number(config?.gaugeMax ?? 100);
  const safeMin = Number.isFinite(min) ? min : 0;
  const safeMax = Number.isFinite(max) && max > safeMin ? max : safeMin + 100;
  const thresholds = config?.thresholdColors || [];

  const valueMapping = applyValueMapping(numericValue, config?.valueMappings);
  const color =
    valueMapping?.color || getColorByThreshold(numericValue, thresholds, '#366CE4');
  const label =
    valueMapping?.text !== undefined
      ? valueMapping.text
      : formatDisplayValue(
        numericValue,
        config?.unit,
        config?.decimalPlaces,
        config?.conversionFactor,
        config?.unitId,
      );

  const ratio =
    safeMax > safeMin
      ? clamp((numericValue! - safeMin) / (safeMax - safeMin), 0, 1)
      : 0;

  return (
    <div className="flex h-full w-full flex-col justify-center gap-1 px-3">
      <div className="flex items-baseline justify-between">
        <span className="truncate text-xs text-(--color-text-3)">
          {config?.unit || ''}
        </span>
        <span
          className="font-semibold tabular-nums"
          style={{ color, fontSize: 18 }}
        >
          {label}
        </span>
      </div>
      <div
        className="relative w-full overflow-hidden rounded"
        style={{ height: 14, background: 'var(--color-fill-2, #f0f0f0)' }}
      >
        <div
          className="absolute left-0 top-0 h-full rounded transition-all"
          style={{ width: `${ratio * 100}%`, background: color }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-(--color-text-4)">
        <span>{safeMin}</span>
        <span>{safeMax}</span>
      </div>
    </div>
  );
};

export default ComBarGauge;
