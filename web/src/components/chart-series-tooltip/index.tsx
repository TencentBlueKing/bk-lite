import React from 'react';
import { TooltipProps } from 'recharts';

interface ChartSeriesTooltipItem {
  key?: React.Key;
  color?: string;
  description?: React.ReactNode;
  value?: React.ReactNode;
  sortValue?: number;
}

export interface ChartSeriesTooltipProps
  extends Omit<TooltipProps<any, string>, 'content'> {
  visible?: boolean;
  maxHeight?: number;
  maxWidth?: number;
  rowAlign?: 'start' | 'center';
  renderTitle: (label: unknown) => React.ReactNode;
  getItems: (payload: any[]) => ChartSeriesTooltipItem[];
}

const ChartSeriesTooltip: React.FC<ChartSeriesTooltipProps> = ({
  active,
  payload,
  label,
  visible = true,
  maxHeight,
  maxWidth,
  rowAlign = 'start',
  renderTitle,
  getItems,
}) => {
  if (!(active && payload?.length && visible)) {
    return null;
  }

  const items = [...getItems(payload)].sort((a, b) => {
    if (typeof a.sortValue === 'number' && typeof b.sortValue === 'number') {
      return b.sortValue - a.sortValue;
    }
    return 0;
  });

  return (
    <div
      className="mt-[10px] max-h-[300px] overflow-y-auto rounded-[5px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-[10px] text-[14px]"
      style={{
        ...(maxHeight ? { maxHeight: `${maxHeight}px` } : {}),
        ...(maxWidth ? { maxWidth: `${maxWidth}px` } : {}),
        pointerEvents: 'auto',
      }}
    >
      <p className="label font-[600]">{renderTitle(label)}</p>
      {items.map((item, index) => (
        <div key={item.key ?? index}>
          <div
            className={`mt-[4px] flex text-[13px] ${
              rowAlign === 'center' ? 'items-center' : 'items-start'
            }`}
          >
            <span
              className="mr-[5px] h-[10px] min-w-[10px] rounded-full"
              style={{
                backgroundColor: item.color,
                marginTop: rowAlign === 'center' ? 0 : '5px',
              }}
            ></span>
            <span className="flex-1">{item.description}</span>
            {item.value !== undefined && item.value !== null && (
              <span className="ml-[10px] whitespace-nowrap font-[600]">
                {item.value}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

export default ChartSeriesTooltip;
