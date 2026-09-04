import React from 'react';
import { Input } from 'antd';
import type { SearchProps } from 'antd/es/input/Search';
import ToolbarSplitShell from '@/components/toolbar-split-shell';

const { Search } = Input;

export interface SearchActionBarProps {
  searchProps: SearchProps;
  actions?: React.ReactNode;
  className?: string;
  searchClassName?: string;
  spacing?: 'default' | 'flush';
}

const SearchActionBar: React.FC<SearchActionBarProps> = ({
  searchProps,
  actions,
  className = '',
  searchClassName = '',
  spacing = 'default',
}) => {
  const { className: rawSearchClassName, allowClear, enterButton, ...restSearchProps } = searchProps;
  const spacingClassName = spacing === 'flush' ? '!mb-0' : undefined;

  return (
    <ToolbarSplitShell
      className={`${spacingClassName || ''} ${className}`.trim()}
      trailing={(
        <>
          <Search
            allowClear={allowClear ?? true}
            enterButton={enterButton ?? true}
            className={`w-60 ${rawSearchClassName || ''} ${searchClassName}`.trim()}
            {...restSearchProps}
          />
          {actions}
        </>
      )}
    />
  );
};

export default SearchActionBar;
