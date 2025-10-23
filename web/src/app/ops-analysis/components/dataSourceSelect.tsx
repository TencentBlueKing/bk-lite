import React from 'react';
import { Select } from 'antd';
import { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

interface DataSourceSelectProps {
  loading?: boolean;
  placeholder?: string;
  style?: any;
  value?: any;
  disabled?: boolean;
  dataSources?: DatasourceItem[];
  onChange?: (value: any) => void;
  onDataSourceChange?: (dataSource: DatasourceItem | undefined) => void;
}

const DataSourceSelect: React.FC<DataSourceSelectProps> = ({
  loading = false,
  placeholder,
  style = { width: '100%' },
  value,
  disabled = false,
  dataSources = [],
  onChange,
  onDataSourceChange,
}) => {
    
  const formatOptions = (sources: DatasourceItem[]) => {
    return sources.map((item) => ({
      label: `${item.name}（${item.rest_api}）`,
      value: item.id,
      title: item.desc,
    }));
  };


  const handleChange = (val: any) => {
    onChange?.(val);
    const selectedSource = dataSources.find((item) => item.id === val);
    onDataSourceChange?.(selectedSource);
  };

  return (
    <Select
      loading={loading}
      options={formatOptions(dataSources)}
      placeholder={placeholder}
      style={style}
      value={value}
      disabled={disabled}
      onChange={handleChange}
    />
  );
};

export default DataSourceSelect;
