import React, { useEffect, useRef, useState } from 'react';
import { Spin, Empty } from 'antd';
import {
  getColorByThreshold,
  formatDisplayValue,
  ThresholdColorConfig,
} from '@/app/ops-analysis/utils/thresholdUtils';
import { DEFAULT_THRESHOLD_COLORS } from '@/app/ops-analysis/constants/threshold';
import { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import {
  getOpsChartTheme,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/utils/chartTheme';
import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';

interface ComSingleProps {
  rawData: unknown;
  loading?: boolean;
  config?: ValueConfig;
  onReady?: (ready: boolean) => void;
}

const ComSingle: React.FC<ComSingleProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
}) => {
  const chartTheme = getOpsChartTheme(resolveOpsChartThemeName());
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  const extractValue = (data: unknown): number | string | null => {
    if (data === null || data === undefined) {
      return null;
    }

    const selectedField = config?.selectedFields?.[0];

    if (selectedField) {
      const extracted = getValueByPath(data, selectedField);
      if (extracted !== undefined && extracted !== null) {
        return typeof extracted === 'number' || typeof extracted === 'string'
          ? extracted
          : null;
      }
    }

    if (typeof data === 'number' || typeof data === 'string') {
      return data;
    }

    if (Array.isArray(data) && data.length > 0) {
      const firstItem = data[0];
      if (firstItem && typeof firstItem === 'object') {
        const values = Object.values(firstItem as Record<string, unknown>);
        for (const val of values) {
          if (typeof val === 'number') return val;
        }
        for (const val of values) {
          if (typeof val === 'string' && !isNaN(parseFloat(val))) return val;
        }
      }
    }

    if (typeof data === 'object' && data !== null) {
      const values = Object.values(data as Record<string, unknown>);
      for (const val of values) {
        if (typeof val === 'number') return val;
      }
    }

    return null;
  };

  const rawValue = extractValue(rawData);
  const numericValue = rawValue !== null
    ? (typeof rawValue === 'string' ? parseFloat(rawValue) : rawValue)
    : null;

  const thresholds: ThresholdColorConfig[] = config?.thresholdColors ?? DEFAULT_THRESHOLD_COLORS;
  const color = getColorByThreshold(numericValue, thresholds, '#000000');
  const isDataReady = rawValue !== null;
  const displayValue = formatDisplayValue(
    numericValue,
    undefined,
    config?.decimalPlaces,
    config?.conversionFactor
  );
  const unitText = config?.unit?.trim() || '';

  useEffect(() => {
    if (!loading) {
      onReady?.(isDataReady);
    }
  }, [isDataReady, loading, onReady]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const updateSize = () => {
      setContainerSize({
        width: element.clientWidth,
        height: element.clientHeight,
      });
    };

    updateSize();

    const observer = new ResizeObserver(updateSize);
    observer.observe(element);

    return () => observer.disconnect();
  }, []);

  if (loading) {
    return (
      <div className="h-full flex flex-col items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }

  if (!isDataReady || rawValue === null) {
    return (
      <div className="h-full flex flex-col items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  // Format number with thousands separator
  const formatWithThousands = (value: string | number | null): string => {
    if (value === null) return '--';
    const strVal = String(value);
    // If it's a pure number (possibly with decimals), add thousands separator
    const parts = strVal.split('.');
    const intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return parts.length > 1 ? `${intPart}.${parts[1]}` : intPart;
  };

  const displayText = formatWithThousands(displayValue);
  const textLength = Math.max(displayText.length + (unitText.length * 0.5), 1);
  const metricColor = color || chartTheme.singleValueColor;
  const adaptiveFontSize = (() => {
    const { width, height } = containerSize;
    if (!width || !height) return 32;

    const heightBasedSize = height * 0.45;
    const widthBasedSize = width / Math.max(textLength * 0.55, 2.4);
    return Math.max(24, Math.min(48, Math.min(heightBasedSize, widthBasedSize)));
  })();

  return (
    <div
      ref={containerRef}
      className="h-full overflow-hidden flex flex-col justify-center px-2"
    >
      <div
        className="font-semibold leading-none"
        style={{
          color: metricColor,
          fontSize: adaptiveFontSize,
          letterSpacing: '-0.02em',
        }}
      >
        {displayText}
        {unitText && (
          <span
            style={{
              fontSize: adaptiveFontSize * 0.55,
              marginLeft: 2,
            }}
          >
            {unitText}
          </span>
        )}
      </div>
    </div>
  );
};

export default ComSingle;
