import React, { useState, useEffect, useRef, useMemo } from 'react';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { randomColorForLegend } from '@/app/ops-analysis/utils/randomColorForChart';

interface ChartLegendProps {
  data: Array<{ name: string }>;
  colors?: string[];
  onSelectionChange?: (selected: Record<string, boolean>) => void;
}

const ChartLegend: React.FC<ChartLegendProps> = ({
  data = [],
  colors = randomColorForLegend(),
  onSelectionChange,
}) => {
  const [selectedLegend, setSelectedLegend] = useState<string[]>([]);
  const onSelectionChangeRef = useRef(onSelectionChange);
  onSelectionChangeRef.current = onSelectionChange;

  const legendData = useMemo(
    () =>
      data
        .map((item) => item.name)
        .filter((item): item is string => ![undefined, null, ''].includes(item)),
    [data]
  );

  const legendKey = legendData.join('\x00');

  useEffect(() => {
    setSelectedLegend([]);
    onSelectionChangeRef.current?.({});
  }, [legendKey]);

  const buildSelectedMap = (active: string[]): Record<string, boolean> => {
    if (active.length === 0) {
      return {};
    }
    return Object.fromEntries(
      legendData.map((n) => [n, active.includes(n)])
    );
  };

  const handleLegend = (item: string) => {
    const alreadySelected = selectedLegend.includes(item);
    let newSelectedLegend: string[] = [...selectedLegend];

    if (alreadySelected) {
      const index = newSelectedLegend.findIndex((r) => r === item);
      newSelectedLegend.splice(index, 1);
    } else {
      newSelectedLegend.push(item);
      if (newSelectedLegend.length === legendData.length) {
        newSelectedLegend = [];
      }
    }

    setSelectedLegend(newSelectedLegend);
    onSelectionChangeRef.current?.(buildSelectedMap(newSelectedLegend));
  };

  const isActive = (item: string) => {
    return selectedLegend.length === 0 || selectedLegend.includes(item);
  };

  const handleWheel: React.WheelEventHandler<HTMLDivElement> = (event) => {
    event.stopPropagation();
  };

  return (
    <div
      className="chart-legend h-full min-h-0 overflow-hidden"
      onWheel={handleWheel}
    >
      <div className="h-full min-h-0 flex items-center">
        <div className="w-full max-h-full min-h-0 flex flex-col">
          <div className="flex-shrink-0">
            <table className="chart-legend-table w-full table-fixed border-collapse">
              <thead>
                <tr>
                  <th className="text-left px-2 py-1.5 text-xs text-[var(--color-text-2)] border-b border-[var(--color-border-1)] bg-[var(--color-fill-2)]">
                    维度
                    <span className="text-[var(--color-text-3)]">
                      ({legendData.length})
                    </span>
                  </th>
                </tr>
              </thead>
            </table>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden pr-1">
            <table className="chart-legend-table w-full table-fixed border-collapse">
              <tbody>
                {legendData.map((item, index) => (
                  <tr
                    key={`${item}-${index}`}
                    className={`
                      cursor-pointer transition-all duration-200
                      ${isActive(item) ? 'opacity-100' : 'opacity-50'}
                      hover:bg-[var(--color-fill-2)]
                      ${index % 2 === 0 ? 'bg-[var(--color-fill-1)]' : 'bg-transparent'}
                    `}
                    onClick={() => handleLegend(item)}
                  >
                    <td className="px-2 py-1 w-full max-w-0">
                      <div className="flex items-center gap-2 min-w-0 w-full">
                        <div
                          className="w-4 h-1 flex-shrink-0"
                          style={{
                            backgroundColor: isActive(item)
                              ? colors[index % colors.length]
                              : 'var(--color-fill-4)',
                          }}
                        />
                        <EllipsisWithTooltip
                          className="block flex-1 min-w-0 max-w-full overflow-hidden whitespace-nowrap text-ellipsis text-xs leading-relaxed text-[var(--color-text-2)]"
                          text={item || '--'}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChartLegend;
