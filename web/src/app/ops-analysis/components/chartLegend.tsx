import React, { useState, useEffect, useRef, useMemo } from 'react';
import { randomColorForLegend } from '@/app/ops-analysis/utils/randomColorForChart';
import { resolveOpsChartThemeName } from '@/app/ops-analysis/utils/chartTheme';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { shouldEmitLegendReset } from '@/components/chart-legend/selection';

const VERTICAL_LEGEND_WIDTH_PX = 120;

interface LegendItem {
  name: string;
  value?: number;
}

interface ChartLegendProps {
  data: LegendItem[];
  colors?: string[];
  /** 布局方向：vertical 右侧竖排（默认），horizontal 顶部横排 */
  layout?: 'vertical' | 'horizontal';
  /** 是否显示百分比（饼图用） */
  showPercent?: boolean;
  textColor?: string;
  scale?: number;
  onSelectionChange?: (selected: Record<string, boolean>) => void;
}

const ChartLegend: React.FC<ChartLegendProps> = ({
  data = [],
  colors,
  layout = 'vertical',
  showPercent = false,
  textColor,
  scale = 1,
  onSelectionChange,
}) => {
  const themeName = resolveOpsChartThemeName();
  const defaultColors = useMemo(() => randomColorForLegend(themeName), [themeName]);
  const chartColors = colors || defaultColors;

  const [selectedLegend, setSelectedLegend] = useState<string[]>([]);
  const onSelectionChangeRef = useRef(onSelectionChange);
  const previousLegendKeyRef = useRef<string | null>(null);
  onSelectionChangeRef.current = onSelectionChange;

  const legendData = useMemo(
    () => data.filter((item) => item.name != null && item.name !== ''),
    [data]
  );

  const legendKey = legendData.map((d) => d.name).join('\x00');

  useEffect(() => {
    setSelectedLegend((prev) => (prev.length === 0 ? prev : []));
    const previousKey = previousLegendKeyRef.current;
    previousLegendKeyRef.current = legendKey;
    if (shouldEmitLegendReset(previousKey, legendKey)) {
      onSelectionChangeRef.current?.({});
    }
  }, [legendKey]);

  const total = useMemo(() => {
    if (!showPercent) return 0;
    return legendData.reduce((sum, item) => sum + (item.value || 0), 0);
  }, [legendData, showPercent]);

  const buildSelectedMap = (active: string[]): Record<string, boolean> => {
    if (active.length === 0) return {};
    return Object.fromEntries(
      legendData.map((item) => [item.name, active.includes(item.name)])
    );
  };

  const handleClick = (name: string) => {
    let newSelected = [...selectedLegend];
    if (newSelected.includes(name)) {
      newSelected = newSelected.filter((n) => n !== name);
    } else {
      newSelected.push(name);
      if (newSelected.length === legendData.length) {
        newSelected = [];
      }
    }
    setSelectedLegend(newSelected);
    onSelectionChangeRef.current?.(buildSelectedMap(newSelected));
  };

  const isActive = (name: string) => {
    return selectedLegend.length === 0 || selectedLegend.includes(name);
  };

  if (layout === 'horizontal') {
    return (
      <div
        className="flex shrink-0 flex-wrap items-center"
        style={{
          columnGap: 16 * scale,
          rowGap: 4 * scale,
          paddingLeft: 8 * scale,
          paddingRight: 8 * scale,
          paddingBottom: 8 * scale,
        }}
      >
        {legendData.map((item, index) => (
          <div
            key={`${item.name}-${index}`}
            className="flex min-w-0 cursor-pointer select-none items-center"
            onClick={() => handleClick(item.name)}
            style={{ gap: 6 * scale, opacity: isActive(item.name) ? 1 : 0.4 }}
          >
            <span
              className="inline-block shrink-0 rounded-sm"
              style={{
                backgroundColor: chartColors[index % chartColors.length],
                height: 10 * scale,
                width: 10 * scale,
              }}
            />
            <span
              className="min-w-0 max-w-40"
              style={{ color: textColor, fontSize: 12 * scale }}
            >
              <EllipsisWithTooltip
                className="overflow-hidden text-ellipsis whitespace-nowrap text-[var(--color-text-2)]"
                text={item.name}
              />
            </span>
          </div>
        ))}
      </div>
    );
  }

  // vertical layout (right side)
  return (
    <div
      className="flex h-full min-h-0 shrink-0 min-w-0"
      style={{ width: VERTICAL_LEGEND_WIDTH_PX * scale }}
    >
      <div
        className="h-full min-h-0 w-full min-w-0 overflow-y-auto"
        data-testid="chart-legend-scroll"
        style={{
          paddingBottom: 4 * scale,
          paddingTop: 4 * scale,
        }}
      >
        {legendData.map((item, index) => {
          const percent = showPercent && total > 0
            ? ((item.value || 0) / total * 100).toFixed(1)
            : null;
          const label = percent != null ? `${item.name} (${percent}%)` : item.name;

          return (
            <div
              key={`${item.name}-${index}`}
              className="flex w-full min-w-0 cursor-pointer select-none items-center rounded transition-colors hover:bg-[var(--color-fill-2)]"
              onClick={() => handleClick(item.name)}
              style={{
                gap: 8 * scale,
                opacity: isActive(item.name) ? 1 : 0.4,
                padding: `${4 * scale}px ${8 * scale}px`,
              }}
            >
              <span
                className="inline-block shrink-0 rounded-sm"
                style={{
                  backgroundColor: chartColors[index % chartColors.length],
                  height: 10 * scale,
                  width: 10 * scale,
                }}
              />
              <span
                className="min-w-0 flex-1"
                style={{ color: textColor, fontSize: 12 * scale }}
              >
                <EllipsisWithTooltip
                  className="overflow-hidden text-ellipsis whitespace-nowrap text-[var(--color-text-2)]"
                  text={label}
                />
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ChartLegend;
