import React, { useEffect, useState, useRef } from 'react';
import { Spin, Empty } from 'antd';
import { formatNumericValue } from '@/app/log/utils/common';

interface ComSingleProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const ComSingle: React.FC<ComSingleProps> = ({
  rawData,
  loading = false,
  config
}) => {
  const [displayValue, setDisplayValue] = useState<number>();
  const [fontSize, setFontSize] = useState<number>(64);
  const containerRef = useRef<HTMLDivElement>(null);

  // 处理数据
  useEffect(() => {
    if (!loading && rawData) {
      let value = config?.getData?.(rawData);
      // fallback: 没有 getData 时，通过 displayMaps 从 rawData 中提取值
      if (value === undefined && config?.displayMaps?.value) {
        const field = config.displayMaps.value;
        if (Array.isArray(rawData) && rawData.length > 0) {
          const parsed = parseFloat(rawData[0][field]);
          value = isNaN(parsed) ? undefined : parsed;
        } else if (
          rawData &&
          typeof rawData === 'object' &&
          !Array.isArray(rawData)
        ) {
          const parsed = parseFloat(rawData[field]);
          value = isNaN(parsed) ? undefined : parsed;
        }
      }
      setDisplayValue(value);
    }
  }, [rawData, loading]);

  // 动态调整字体大小
  useEffect(() => {
    const updateFontSize = () => {
      if (containerRef.current) {
        const containerWidth = containerRef.current.clientWidth - 32;
        const containerHeight = containerRef.current.clientHeight;
        const digits = String(displayValue ?? '').length || 1;

        // 高度约束：确保文本不超出容器高度（lineHeight=1.2）
        const maxByHeight = containerHeight / 1.4;
        // 宽度约束：保守估计大号粗体数字的占宽
        const maxByWidth = containerWidth / Math.max(digits * 0.72, 1);
        const calculatedSize = Math.max(
          20,
          Math.min(maxByHeight, maxByWidth, 104)
        );
        setFontSize(calculatedSize);
      }
    };

    updateFontSize();

    // 监听容器大小变化
    const resizeObserver = new ResizeObserver(() => {
      updateFontSize();
    });

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => {
      resizeObserver.disconnect();
    };
  }, [displayValue]);

  if (loading) {
    return (
      <div className="h-full flex flex-col items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }

  if (!displayValue && displayValue !== 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="flex h-full w-full items-center justify-center px-2"
    >
      <div className="flex h-full w-full items-center rounded-2xl bg-[linear-gradient(180deg,rgba(79,124,243,0.08)_0%,rgba(79,124,243,0.02)_100%)] px-5 py-4">
        <div
          className="w-full overflow-hidden text-center select-none font-semibold text-[var(--color-text-1)] transition-all duration-300"
          style={{
            fontSize: `${fontSize}px`,
            color: config?.color || 'var(--color-text-1)',
            lineHeight: 1,
            letterSpacing: '-0.04em'
          }}
        >
          {formatNumericValue(displayValue)}
        </div>
      </div>
    </div>
  );
};

export default ComSingle;
