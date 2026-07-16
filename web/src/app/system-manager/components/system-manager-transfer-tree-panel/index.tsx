import React from 'react';
import { Input } from 'antd';
import { SearchOutlined } from '@ant-design/icons';

interface TransferTreePanelProps {
  children: React.ReactNode;
  maxHeight?: number;
  onSearchChange: (value: string) => void;
  searchPlaceholder: string;
  searchValue: string;
}

const TransferTreePanel: React.FC<TransferTreePanelProps> = ({
  children,
  maxHeight = 250,
  onSearchChange,
  searchPlaceholder,
  searchValue,
}) => {
  return (
    <div className="flex flex-col w-full">
      <div className="p-2">
        <Input
          prefix={<SearchOutlined />}
          placeholder={searchPlaceholder}
          value={searchValue}
          onChange={(e) => onSearchChange(e.target.value)}
          allowClear
        />
      </div>
      <div className="overflow-auto p-1" style={{ maxHeight }}>
        {children}
      </div>
    </div>
  );
};

export default TransferTreePanel;
