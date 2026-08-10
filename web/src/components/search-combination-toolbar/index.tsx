import React from 'react';
import SearchCombination from '@/components/search-combination';
import type { FieldConfig, SearchFilters } from '@/components/search-combination/types';
import ToolbarSplitShell from '@/components/toolbar-split-shell';

export interface SearchCombinationToolbarProps {
  fieldConfigs: FieldConfig[];
  onSearchChange: (filters: SearchFilters) => void;
  actions?: React.ReactNode;
  className?: string;
  fieldWidth?: number;
  selectWidth?: number;
  actionsClassName?: string;
}

const SearchCombinationToolbar: React.FC<SearchCombinationToolbarProps> = ({
  fieldConfigs,
  onSearchChange,
  actions,
  className = '',
  fieldWidth = 120,
  selectWidth = 300,
  actionsClassName = 'flex items-center gap-3',
}) => {
  return (
    <ToolbarSplitShell
      className={`mb-0 ${className}`.trim()}
      leadingClassName="items-center"
      trailingClassName={actionsClassName}
      leading={(
        <SearchCombination
          fieldConfigs={fieldConfigs}
          onChange={onSearchChange}
          fieldWidth={fieldWidth}
          selectWidth={selectWidth}
        />
      )}
      trailing={actions}
    />
  );
};

export default SearchCombinationToolbar;
