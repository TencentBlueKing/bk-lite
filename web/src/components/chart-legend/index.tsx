import React, { useEffect, useMemo, useRef, useState } from 'react';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import type { ChartLegendSelection } from './selection';

export type { ChartLegendSelection } from './selection';

export interface ChartLegendItem {
  name: string;
  value?: number;
}

export interface ChartLegendProps {
  data: ChartLegendItem[];
  colors: string[];
  variant?: 'list' | 'table';
  layout?: 'vertical' | 'horizontal';
  showPercent?: boolean;
  title?: React.ReactNode;
  className?: string;
  onSelectionChange?: (selected: ChartLegendSelection) => void;
}

const buildSelectionMap = (
  activeNames: string[],
  legendData: ChartLegendItem[],
): ChartLegendSelection => {
  if (activeNames.length === 0) {
    return {};
  }

  return Object.fromEntries(
    legendData.map((item) => [item.name, activeNames.includes(item.name)]),
  );
};

const ChartLegend: React.FC<ChartLegendProps> = ({
  data = [],
  colors = [],
  variant = 'list',
  layout = 'vertical',
  showPercent = false,
  title,
  className = '',
  onSelectionChange,
}) => {
  const [selectedLegend, setSelectedLegend] = useState<string[]>([]);
  const onSelectionChangeRef = useRef(onSelectionChange);
  onSelectionChangeRef.current = onSelectionChange;

  const legendData = useMemo(
    () => data.filter((item) => item.name != null && item.name !== ''),
    [data],
  );
  const legendKey = legendData.map((item) => item.name).join('\x00');

  useEffect(() => {
    setSelectedLegend([]);
    onSelectionChangeRef.current?.({});
  }, [legendKey]);

  const total = useMemo(() => {
    if (!showPercent) {
      return 0;
    }

    return legendData.reduce((sum, item) => sum + Number(item.value || 0), 0);
  }, [legendData, showPercent]);

  const handleClick = (name: string) => {
    let nextSelected = [...selectedLegend];

    if (nextSelected.includes(name)) {
      nextSelected = nextSelected.filter((item) => item !== name);
    } else {
      nextSelected.push(name);
      if (nextSelected.length === legendData.length) {
        nextSelected = [];
      }
    }

    setSelectedLegend(nextSelected);
    onSelectionChangeRef.current?.(buildSelectionMap(nextSelected, legendData));
  };

  const isActive = (name: string) =>
    selectedLegend.length === 0 || selectedLegend.includes(name);

  const getItemColor = (index: number, active: boolean) => {
    if (!active) {
      return '#d1d5db';
    }

    return colors[index % colors.length] || '#9ca3af';
  };

  if (variant === 'table') {
    return (
      <div className={`h-full min-w-0 flex flex-col overflow-hidden ${className}`}>
        <div className="flex-1 min-h-0 overflow-x-hidden overflow-y-auto">
          <table className="w-full table-fixed border-collapse">
            {title ? (
              <thead className="sticky top-0 z-10">
                <tr>
                  <th className="border-b border-[var(--color-border-2)] bg-[var(--color-fill-2)] px-2 py-1.5 text-left text-xs font-medium text-[var(--color-text-3)]">
                    {title}
                    <span className="ml-1 text-[var(--color-text-4)]">
                      ({legendData.length})
                    </span>
                  </th>
                </tr>
              </thead>
            ) : null}
            <tbody>
              {legendData.map((item, index) => (
                <tr
                  key={`${item.name}-${index}`}
                  className={`
                    ${isActive(item.name) ? 'opacity-100' : 'opacity-45'}
                    ${index % 2 === 0 ? '' : 'bg-[var(--color-fill-1)]'}
                  `}
                >
                  <td className="w-full max-w-0 px-2 py-1">
                    <button
                      type="button"
                      className="flex w-full min-w-0 items-center gap-2 rounded px-0 text-left transition-colors duration-200 hover:bg-[var(--color-fill-2)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-6)]"
                      onClick={() => handleClick(item.name)}
                      aria-pressed={isActive(item.name)}
                      aria-label={item.name}
                    >
                      <span
                        className="h-1 w-4 flex-shrink-0 rounded-sm"
                        style={{
                          backgroundColor: getItemColor(index, isActive(item.name)),
                        }}
                      />
                      <EllipsisWithTooltip
                        className="block w-full min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-xs leading-relaxed text-[var(--color-text-2)]"
                        text={item.name || '--'}
                      />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (layout === 'horizontal') {
    return (
      <div className={`shrink-0 flex flex-wrap items-center gap-x-4 gap-y-1 px-2 pb-2 ${className}`}>
        {legendData.map((item, index) => (
          <button
            key={`${item.name}-${index}`}
            type="button"
            className="flex select-none items-center gap-1.5 rounded px-1 py-0.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-6)]"
            onClick={() => handleClick(item.name)}
            aria-pressed={isActive(item.name)}
            aria-label={item.name}
            style={{ opacity: isActive(item.name) ? 1 : 0.4 }}
          >
            <span
              className="inline-block h-2.5 w-2.5 flex-shrink-0 rounded-sm"
              style={{ backgroundColor: getItemColor(index, isActive(item.name)) }}
            />
            <span className="text-xs text-[var(--color-text-2)]">{item.name}</span>
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className={`min-w-36 max-w-80 shrink-0 h-full flex items-center ${className}`}>
      <div className="max-h-full overflow-y-auto py-1">
        {legendData.map((item, index) => {
          const active = isActive(item.name);
          const percent = showPercent && total > 0
            ? ((Number(item.value || 0) / total) * 100).toFixed(1)
            : null;

          return (
            <button
              key={`${item.name}-${index}`}
              type="button"
              className="flex w-full select-none items-center gap-2 rounded px-2 py-1 text-left transition-colors hover:bg-[var(--color-fill-2)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-6)]"
              onClick={() => handleClick(item.name)}
              aria-pressed={active}
              aria-label={item.name}
              style={{ opacity: active ? 1 : 0.4 }}
            >
              <span
                className="inline-block h-2.5 w-2.5 flex-shrink-0 rounded-sm"
                style={{ backgroundColor: getItemColor(index, active) }}
              />
              <span className="inline-block max-w-64 truncate text-xs text-[var(--color-text-2)]">
                {item.name}
                {percent != null ? ` (${percent}%)` : ''}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default ChartLegend;
