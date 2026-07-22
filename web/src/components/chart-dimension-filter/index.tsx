import React, { memo, useCallback, useMemo } from 'react';

export interface ChartDimensionFilterProps {
  data: Array<Record<string, any>>;
  colors: string[];
  visibleAreas: Array<string | number>;
  details: Record<string, any>;
  onLegendClick: (key: string) => void;
  title: string;
}

const getChartAreaKeys = (arr: Array<Record<string, any>>) => {
  const keys = new Set<string>();
  arr.forEach((obj) => {
    Object.keys(obj).forEach((key) => {
      if (key.includes('value')) {
        keys.add(key);
      }
    });
  });
  return Array.from(keys);
};

const buildDimensionLabel = (detail: any) => {
  const arr = (detail || []).map((item: any) => `${item.label}: ${item.value}`);
  return arr.join('-') || '--';
};

const triggerOnEnterOrSpace = (
  event: React.KeyboardEvent<HTMLButtonElement>,
  action: () => void
) => {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    action();
  }
};

const ChartDimensionFilter: React.FC<ChartDimensionFilterProps> = memo(
  ({ data, colors, visibleAreas, details, onLegendClick, title }) => {
    const chartAreaKeys = useMemo(() => getChartAreaKeys(data), [data]);

    const getDimensionLabel = useCallback(
      (key: string) => buildDimensionLabel(details[key]),
      [details]
    );

    return (
      <div
        className="ml-[10px] shrink-0 bg-[var(--color-bg-1)]"
        style={{ width: 'clamp(120px, 20%, 200px)' }}
      >
        <div className="bg-[var(--color-fill-2)] p-[4px] text-center text-[14px] font-[800]">
          {title}
        </div>
        <ul
          className="overflow-y-auto text-[12px]"
          style={{ height: 'calc(100% - 40px)' }}
        >
          {chartAreaKeys.map((key, index) => {
            const dimensionLabel = getDimensionLabel(key);
            const isVisible = visibleAreas.includes(key);
            return (
              <li
                key={key}
                className={index % 2 === 1 ? 'bg-[var(--color-fill-1)]' : ''}
              >
                <button
                  type="button"
                  className={`flex h-[30px] w-full items-center px-[4px] text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)] focus-visible:ring-inset ${
                    isVisible
                      ? 'text-[var(--color-text-2)]'
                      : 'text-[var(--ant-color-text-disabled)]'
                  }`}
                  aria-pressed={isVisible}
                  onClick={() => onLegendClick(key)}
                  onKeyDown={(event) =>
                    triggerOnEnterOrSpace(event, () => onLegendClick(key))
                  }
                >
                  <span
                    className="mr-[10px] h-[4px] w-[10px]"
                    style={{
                      background: isVisible
                        ? colors[index]
                        : 'var(--ant-color-bg-container-disabled)',
                    }}
                  ></span>
                  <span className="min-w-0 flex-1 truncate" title={dimensionLabel}>
                    {dimensionLabel}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    );
  }
);

ChartDimensionFilter.displayName = 'ChartDimensionFilter';

export default ChartDimensionFilter;
