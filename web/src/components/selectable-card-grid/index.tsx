import React from 'react';
import { Tag } from 'antd';
import Icon from '@/components/icon';

export interface SelectableCardItem {
  icon?: string;
  title: string;
  tag?: string;
  description?: string;
  value: string | number;
}

interface SelectableCardGridProps {
  data: SelectableCardItem[];
  value?: string | number | Array<string | number>;
  onChange?: (value: string | number | Array<string | number>) => void;
  cardWidth?: number;
  style?: React.CSSProperties;
  selectionMode?: 'single' | 'multiple';
}

const getColorWithOpacity = (cssVar: string, opacity: number): string => {
  return `color-mix(in srgb, var(${cssVar}) ${opacity * 100}%, transparent)`;
};

const SelectableCardGrid: React.FC<SelectableCardGridProps> = ({
  data = [],
  value,
  onChange,
  cardWidth,
  style,
  selectionMode = 'multiple',
}) => {
  const currentValues = Array.isArray(value)
    ? value
    : value === undefined || value === null
      ? []
      : [value];

  const handleCardClick = (item: SelectableCardItem) => {
    if (selectionMode === 'single') {
      onChange?.(item.value);
      return;
    }

    const exists = currentValues.includes(item.value);
    const nextValue = exists
      ? currentValues.filter((v) => v !== item.value)
      : [...currentValues, item.value];
    onChange?.(nextValue);
  };

  return (
    <div
      className={cardWidth ? 'grid gap-4' : 'grid grid-cols-3 gap-4'}
      style={{
        gridAutoRows: '1fr',
        ...(cardWidth ? { gridTemplateColumns: `repeat(auto-fill, ${cardWidth}px)` } : {}),
        ...style,
      }}
    >
      {data.map((item, index) => {
        const isSelected = currentValues.includes(item.value);
        return (
          <div
            key={index}
            onClick={() => handleCardClick(item)}
            style={{
              width: cardWidth ? `${cardWidth}px` : undefined,
              backgroundColor: isSelected
                ? getColorWithOpacity('--color-primary', 0.04)
                : undefined,
            }}
            className={`group cursor-pointer rounded-lg border-2 bg-[var(--color-bg-1)] p-3 shadow-md transition-all duration-300 ease-in-out hover:shadow-lg ${
              isSelected
                ? 'border-[var(--color-primary)] shadow-[0_8px_24px_rgba(0,112,243,0.2)]'
                : 'border-transparent'
            }`}
          >
            <div className="flex h-full gap-3">
              {item.icon ? (
                <Icon type={item.icon} className="mt-1 flex-shrink-0 text-2xl" />
              ) : null}
              <div className="flex min-w-0 flex-1 flex-col">
                <h2 className="m-0 truncate text-[14px] font-bold" title={item.title}>
                  {item.title}
                </h2>
                {item.tag ? (
                  <div className="mt-1">
                    <Tag color="blue" className="text-[12px]">
                      {item.tag}
                    </Tag>
                  </div>
                ) : null}
                <p
                  className="m-0 mt-1 line-clamp-2 flex-1 text-[12px] text-[var(--color-text-3)]"
                  title={item.description || '--'}
                >
                  {item.description || '--'}
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default SelectableCardGrid;
