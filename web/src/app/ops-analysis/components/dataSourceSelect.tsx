import React, { CSSProperties } from 'react';
import { Select, Tag } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { useTranslation } from '@/utils/i18n';

interface DataSourceSelectProps {
  loading?: boolean;
  placeholder?: string;
  style?: CSSProperties;
  className?: string;
  value?: number;
  disabled?: boolean;
  dataSources?: DatasourceItem[];
  onChange?: (value: number) => void;
  onDataSourceChange?: (dataSource: DatasourceItem | undefined) => void;
  showSearch?: boolean;
  onSearch?: (value: string) => void;
}

const DataSourceSelect: React.FC<DataSourceSelectProps> = ({
  loading = false,
  placeholder,
  style = { width: '100%' },
  className,
  value,
  disabled = false,
  dataSources = [],
  onChange,
  onDataSourceChange,
  showSearch = false,
  onSearch,
}) => {
  const { t } = useTranslation();

  const formatOptions = (sources: DatasourceItem[]) => {
    return sources.map((item) => ({
      label: (
        <div className="flex items-center justify-between w-full">
          <span>{`${item.name}（${item.rest_api}）`}</span>
          {item.hasAuth === false && (
            <Tag icon={<LockOutlined />} color="warning" className="ml-2">
              {t('common.noAuth')}
            </Tag>
          )}
        </div>
      ),
      value: item.id,
      title: item.desc,
      disabled: item.hasAuth === false,
      searchText: `${item.name} ${item.rest_api}`,
    }));
  };

  const handleChange = (val: number) => {
    onChange?.(val);
    const selectedSource = dataSources.find((item) => item.id === val);
    onDataSourceChange?.(selectedSource);
  };

  const filterByNameOrApi = (
    input: string,
    option?: { searchText?: string },
  ) => {
    if (!option?.searchText) return false;
    return option.searchText.toLowerCase().includes(input.toLowerCase());
  };

  return (
    <Select
      loading={loading}
      options={formatOptions(dataSources)}
      placeholder={placeholder}
      style={style}
      className={className}
      value={value}
      disabled={disabled}
      onChange={handleChange}
      showSearch={showSearch}
      filterOption={onSearch ? false : showSearch ? filterByNameOrApi : undefined}
      onSearch={onSearch}
    />
  );
};

export default DataSourceSelect;
