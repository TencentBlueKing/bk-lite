import React from 'react';
import Icon from '@/components/icon';
import { ListItem } from '@/app/log/types';
import { SelectCardsProps } from '@/app/log/types/event';

const SelectCards: React.FC<SelectCardsProps> = ({
  data = [],
  value = '',
  onChange,
}) => {
  const handleCardClick = (item: ListItem) => {
    // 只有在点击的不是当前选中项时才切换，实现radio行为
    if (value !== item.value) {
      onChange?.(item.value as string);
    }
  };

  return (
    <div className="flex flex-wrap gap-4">
      {data.map((item, index) => (
        <div
          key={index}
          onClick={() => handleCardClick(item)}
          className={`w-[220px] bg-[var(--color-bg-1)] border-2 ${
            value === item.value
              ? 'border-[var(--color-primary)] shadow-lg border-blue-300'
              : 'border-[var(--color-border-2)]'
          } shadow-md transition-all duration-300 ease-in-out rounded-lg p-3 relative cursor-pointer group hover:shadow-lg`}
        >
          <div className="flex items-center space-x-4 my-1">
            <Icon type={item.icon || ''} className="text-2xl" />
            <h2 className="text-[16px] font-bold m-0">{item.title}</h2>
          </div>
          <p className="text-[var(--color-text-3)] text-[13px]">
            {item.content}
          </p>
        </div>
      ))}
    </div>
  );
};

export default SelectCards;
