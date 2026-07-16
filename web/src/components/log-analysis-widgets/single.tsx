import React, { useEffect, useState } from 'react';
import AutoFitMetricValue from '@/components/auto-fit-metric-value';
import ChartSurface from '@/components/chart-surface';
import { formatNumericValue } from '@/components/log-analysis-widgets/runtime';

export interface LogAnalysisSingleProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const LogAnalysisSingle: React.FC<LogAnalysisSingleProps> = ({
  rawData,
  loading = false,
  config,
}) => {
  const [displayValue, setDisplayValue] = useState<number>();

  useEffect(() => {
    if (!loading && rawData) {
      let value = config?.getData?.(rawData);
      if (value === undefined && config?.displayMaps?.value) {
        const field = config.displayMaps.value;
        if (Array.isArray(rawData) && rawData.length > 0) {
          const parsed = parseFloat(rawData[0][field]);
          value = isNaN(parsed) ? undefined : parsed;
        } else if (rawData && typeof rawData === 'object' && !Array.isArray(rawData)) {
          const parsed = parseFloat(rawData[field]);
          value = isNaN(parsed) ? undefined : parsed;
        }
      }
      setDisplayValue(value);
    }
  }, [config, loading, rawData]);

  return (
    <ChartSurface
      loading={loading}
      hasData={displayValue === 0 || !!displayValue}
      containerClassName="flex h-full w-full items-center justify-center px-2"
      loadingClassName="flex h-full w-full items-center justify-center"
      emptyClassName="flex h-full w-full items-center justify-center"
    >
      <div className="flex h-full w-full items-center rounded-2xl bg-[linear-gradient(180deg,rgba(79,124,243,0.08)_0%,rgba(79,124,243,0.02)_100%)] px-5 py-4">
        <AutoFitMetricValue
          className="w-full"
          valueClassName="w-full justify-center overflow-hidden text-center font-semibold text-[var(--color-text-1)] transition-all duration-300"
          main={formatNumericValue(displayValue)}
          color={config?.color || 'var(--color-text-1)'}
          align="end"
          minFontSize={20}
          resolveFontSize={({ width, height }) => {
            const safeWidth = Math.max(width - 32, 0);
            const digits = String(displayValue ?? '').length || 1;
            const maxByHeight = height / 1.4;
            const maxByWidth = safeWidth / Math.max(digits * 0.72, 1);
            return Math.min(maxByHeight, maxByWidth, 104);
          }}
        />
      </div>
    </ChartSurface>
  );
};

export default LogAnalysisSingle;
