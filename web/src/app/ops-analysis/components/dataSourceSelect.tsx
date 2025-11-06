import React, { CSSProperties } from 'react';
import { Select, Tag } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { useTranslation } from '@/utils/i18n';

interface DataSourceSelectProps {
  loading?: boolean;
  placeholder?: string;
  style?: CSSProperties;
  value?: number;
  disabled?: boolean;
  dataSources?: DatasourceItem[];
  onChange?: (value: number) => void;
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
    }));
  };

  const handleChange = (val: number) => {
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
