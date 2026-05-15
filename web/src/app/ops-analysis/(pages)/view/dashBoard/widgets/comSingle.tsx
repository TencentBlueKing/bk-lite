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

interface ComSingleProps {
  rawData: unknown;
  loading?: boolean;
  config?: ValueConfig;
  onReady?: (ready: boolean) => void;
}

const toAlphaColor = (inputColor: string, alpha: number) => {
  if (inputColor.startsWith('#')) {
    const normalized = inputColor.replace('#', '');
    const hex =
      normalized.length === 3
        ? normalized
          .split('')
          .map((char) => `${char}${char}`)
          .join('')
        : normalized;
    const red = parseInt(hex.slice(0, 2), 16);
    const green = parseInt(hex.slice(2, 4), 16);
    const blue = parseInt(hex.slice(4, 6), 16);
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
  }

  const matched = inputColor.match(/rgba?\(([^)]+)\)/);
  if (matched) {
    const [red, green, blue] = matched[1]
      .split(',')
      .slice(0, 3)
      .map((part) => part.trim());
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
  }

  return inputColor;
};

const getValueByPathForSingle = (obj: unknown, path: string): unknown => {
  if (!obj || !path) return undefined;

  return path.split('.').reduce((current, key) => {
    if (current === null || current === undefined) return undefined;

    if (Array.isArray(current)) {
      const index = parseInt(key, 10);
      if (!isNaN(index) && index >= 0 && index < current.length) {
        return current[index];
      }
      return current.length > 0 && current[0] && typeof current[0] === 'object'
        ? (current[0] as Record<string, unknown>)[key]
        : undefined;
    }

    return (current as Record<string, unknown>)[key];
  }, obj);
};

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
      const extracted = getValueByPathForSingle(data, selectedField);
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
    config?.unit,
    config?.decimalPlaces,
    config?.conversionFactor
  );

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

  const displayText = String(displayValue);
  const textLength = Math.max(displayText.length, 1);
  const metricColor = color || chartTheme.singleValueColor;
  const adaptiveFontSize = (() => {
    const { width, height } = containerSize;
    if (!width || !height) return 42;

    const heightBasedSize = height * 0.42;
    const widthBasedSize = width / Math.max(textLength * 0.6, 2.6);
    return Math.max(36, Math.min(104, Math.min(heightBasedSize, widthBasedSize)));
  })();

  return (
    <div
      ref={containerRef}
      className="relative h-full overflow-hidden flex flex-col items-center justify-center px-5 py-4"
      style={{
        background: `linear-gradient(180deg, ${chartTheme.singleValueSurface} 0%, ${chartTheme.panelSubtleBg} 100%)`,
        borderRadius: 14,
        border: `1px solid ${toAlphaColor(metricColor, 0.08)}`,
      }}
    >
      <div className="relative z-10 flex flex-col items-center justify-center text-center">
        <div
          className="font-bold transition-colors duration-300 leading-none text-center"
          style={{
            color: metricColor,
            fontSize: adaptiveFontSize,
            textShadow: chartTheme.singleValueGlow,
            letterSpacing: '-0.04em',
          }}
        >
          {displayText}
        </div>
      </div>
    </div>
  );
};

export default ComSingle;
