import React, { useCallback, useEffect, useRef, useState } from 'react';
import ChartSurface, {
  type ChartSurfaceProps,
} from '@/components/chart-surface';

export interface ChartWithSidebarLegendProps {
  chart: React.ReactNode;
  legend?: React.ReactNode;
  legendVisible?: boolean;
  legendMode?: 'always' | 'responsive';
  minChartWidthPx?: number;
  legendWidthPx?: number;
  legendGapPx?: number;
  chartPaneClassName?: string;
  legendPaneClassName?: string;
  surfaceProps: Omit<ChartSurfaceProps, 'children'>;
}

const ChartWithSidebarLegend: React.FC<ChartWithSidebarLegendProps> = ({
  chart,
  legend,
  legendVisible = true,
  legendMode = 'always',
  minChartWidthPx = 200,
  legendWidthPx = 160,
  legendGapPx = 8,
  chartPaneClassName = 'flex-1 min-w-0',
  legendPaneClassName = '',
  surfaceProps,
}) => {
  const [showLegend, setShowLegend] = useState(
    legendVisible && legendMode === 'always'
  );
  const observerRef = useRef<ResizeObserver | null>(null);

  const containerCallbackRef = useCallback(
    (node: HTMLDivElement | null) => {
      observerRef.current?.disconnect();
      observerRef.current = null;

      if (!node) {
        return;
      }

      if (legendMode !== 'responsive') {
        setShowLegend(legendVisible);
        return;
      }

      const observer = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const containerWidth = entry.contentRect.width;
          setShowLegend(
            legendVisible &&
              containerWidth >= minChartWidthPx + legendWidthPx + legendGapPx
          );
        }
      });

      observer.observe(node);
      observerRef.current = observer;
    },
    [legendGapPx, legendMode, legendVisible, legendWidthPx, minChartWidthPx]
  );

  useEffect(() => {
    if (legendMode === 'always') {
      setShowLegend(legendVisible);
    }
  }, [legendMode, legendVisible]);

  useEffect(() => {
    return () => {
      observerRef.current?.disconnect();
    };
  }, []);

  return (
    <ChartSurface {...surfaceProps} ref={containerCallbackRef}>
      <div className={chartPaneClassName}>{chart}</div>
      {showLegend && legend ? (
        <div className={legendPaneClassName}>{legend}</div>
      ) : null}
    </ChartSurface>
  );
};

export default ChartWithSidebarLegend;
