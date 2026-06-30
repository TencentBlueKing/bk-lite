import React, { useState, useEffect, useRef, useMemo } from 'react';
import { randomColorForLegend } from '@/app/ops-analysis/utils/randomColorForChart';
import { resolveOpsChartThemeName } from '@/app/ops-analysis/utils/chartTheme';

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
  onSelectionChange?: (selected: Record<string, boolean>) => void;
}

const ChartLegend: React.FC<ChartLegendProps> = ({
  data = [],
  colors,
  layout = 'vertical',
  showPercent = false,
  textColor,
  onSelectionChange,
}) => {
  const themeName = resolveOpsChartThemeName();
  const defaultColors = useMemo(() => randomColorForLegend(themeName), [themeName]);
  const chartColors = colors || defaultColors;

  const [selectedLegend, setSelectedLegend] = useState<string[]>([]);
  const onSelectionChangeRef = useRef(onSelectionChange);
  onSelectionChangeRef.current = onSelectionChange;

  const legendData = useMemo(
    () => data.filter((item) => item.name != null && item.name !== ''),
    [data]
  );

  const legendKey = legendData.map((d) => d.name).join('\x00');

  useEffect(() => {
    setSelectedLegend([]);
    onSelectionChangeRef.current?.({});
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
      <div className="shrink-0 flex flex-wrap items-center gap-x-4 gap-y-1 px-2 pb-2">
        {legendData.map((item, index) => (
          <div
            key={`${item.name}-${index}`}
            className="flex items-center gap-1.5 cursor-pointer select-none"
            onClick={() => handleClick(item.name)}
            style={{ opacity: isActive(item.name) ? 1 : 0.4 }}
          >
            <span
              className="inline-block w-2.5 h-2.5 rounded-sm flex-shrink-0"
              style={{ backgroundColor: chartColors[index % chartColors.length] }}
            />
            <span className="text-xs text-[var(--color-text-2)]" style={{ color: textColor }}>
              {item.name}
            </span>
          </div>
        ))}
      </div>
    );
  }

  // vertical layout (right side)
  return (
    <div className="min-w-36 max-w-80 shrink-0 h-full flex items-center">
      <div className="max-h-full overflow-y-auto py-1">
        {legendData.map((item, index) => {
          const percent = showPercent && total > 0
            ? ((item.value || 0) / total * 100).toFixed(1)
            : null;

          return (
            <div
              key={`${item.name}-${index}`}
              className="flex items-center gap-2 px-2 py-1 cursor-pointer select-none rounded hover:bg-[var(--color-fill-2)] transition-colors"
              onClick={() => handleClick(item.name)}
              style={{ opacity: isActive(item.name) ? 1 : 0.4 }}
            >
              <span
                className="inline-block w-2.5 h-2.5 rounded-sm flex-shrink-0"
                style={{ backgroundColor: chartColors[index % chartColors.length] }}
              />
              <span
                className="inline-block max-w-64 text-xs text-[var(--color-text-2)] truncate"
                style={{ color: textColor }}
              >
                {item.name}
                {percent != null && ` (${percent}%)`}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ChartLegend;
