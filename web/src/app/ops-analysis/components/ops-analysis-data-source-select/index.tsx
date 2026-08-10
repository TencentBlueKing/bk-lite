import React, { CSSProperties } from 'react';
import { Select } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import type { DatasourceItem } from '@/app/ops-analysis/components/ops-analysis-widgets';
import StatusBadgeShell from '@/components/status-badge-shell';
import { useTranslation } from '@/utils/i18n';

export interface OpsAnalysisDataSourceSelectProps {
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

const OpsAnalysisDataSourceSelect: React.FC<OpsAnalysisDataSourceSelectProps> = ({
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
            <span className="ml-2">
              <StatusBadgeShell
                label={
                  <span className="inline-flex items-center gap-1">
                    <LockOutlined />
                    <span>{t('common.noAuth')}</span>
                  </span>
                }
                palette={{
                  textColor: 'var(--color-warning)',
                  backgroundColor:
                    'color-mix(in srgb, var(--color-warning) 12%, transparent)',
                }}
              />
            </span>
          )}
        </div>
      ),
      value: item.id,
      title: item.desc,
      disabled: item.hasAuth === false,
      searchText: `${item.name} ${item.rest_api}`,
    }));
  };

  const handleChange = (selectedValue: number) => {
    onChange?.(selectedValue);
    const selectedSource = dataSources.find((item) => item.id === selectedValue);
    onDataSourceChange?.(selectedSource);
  };

  const filterByNameOrApi = (input: string, option?: { searchText?: string }) => {
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

export default OpsAnalysisDataSourceSelect;
