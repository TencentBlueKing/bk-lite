import type { ReactNode } from 'react';
import { Tag } from 'antd';

export interface SelectableTagFilterOption {
  value: string;
  label: ReactNode;
}

export interface SelectableTagFilterGroupProps {
  options: SelectableTagFilterOption[];
  selectedValues: string[];
  onToggle: (value: string) => void;
  className?: string;
}

const tagClassName =
  'cursor-pointer select-none transition-all duration-200 hover:scale-105';

const SelectableTagFilterGroup = ({
  options,
  selectedValues,
  onToggle,
  className = '',
}: SelectableTagFilterGroupProps) => {
  if (!options.length) {
    return null;
  }

  return (
    <div className={className}>
      {options.map((option) => (
        <Tag
          key={option.value}
          color={selectedValues.includes(option.value) ? 'blue' : 'default'}
          className={tagClassName}
          onClick={() => onToggle(option.value)}
        >
          {option.label}
        </Tag>
      ))}
    </div>
  );
};

export default SelectableTagFilterGroup;
