import React, { useEffect, useState, useRef } from 'react';
import { Spin, Empty } from 'antd';

interface ComSingleProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const ComSingle: React.FC<ComSingleProps> = ({
  rawData,
  loading = false,
  config,
}) => {
  const [displayValue, setDisplayValue] = useState<number>();
  const [fontSize, setFontSize] = useState<number>(100);
  const containerRef = useRef<HTMLDivElement>(null);

  // 处理数据
  useEffect(() => {
    if (!loading && rawData) {
      const value = config?.getData?.(rawData);
      setDisplayValue(value);
    }
  }, [rawData, loading]);

  // 动态调整字体大小
  useEffect(() => {
    const updateFontSize = () => {
      if (containerRef.current) {
        const containerWidth = containerRef.current.clientWidth;
        const containerHeight = containerRef.current.clientHeight;

        // 根据容器大小计算合适的字体大小
        const minDimension = Math.min(containerWidth, containerHeight);
        const calculatedSize = Math.max(50, Math.min(minDimension * 0.6, 300));
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
      className="h-full w-full flex items-center justify-center"
    >
      <div
        className="font-bold text-center select-none transition-all duration-300"
        style={{
          fontSize: `${fontSize}px`,
          color: config?.color || 'var(--color-primary)',
          lineHeight: 1.2,
        }}
      >
        {displayValue}
      </div>
    </div>
  );
};

export default ComSingle;
