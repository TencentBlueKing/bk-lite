import React from 'react';
import { Checkbox, Space, Spin } from 'antd';
import { ClearOutlined } from '@ant-design/icons';
import Collapse from '@/components/collapse';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';

export interface AlarmFiltersValue {
  level: string[];
  state: string[];
  alarm_source: string[];
}

export type AlarmFilterField = keyof AlarmFiltersValue;

export interface AlarmFilterOption {
  value: string;
  label: string;
  color?: string;
}

export interface AlarmFiltersProps {
  filters: AlarmFiltersValue;
  filterSource?: boolean;
  levelOptions: AlarmFilterOption[];
  stateOptions: AlarmFilterOption[];
  sourceOptions?: AlarmFilterOption[];
  sourceLoading?: boolean;
  onFilterChange: (vals: string[], field: AlarmFilterField) => void;
  clearFilters: (field: AlarmFilterField) => void;
}

const AlarmFilters: React.FC<AlarmFiltersProps> = ({
  filters,
  filterSource = true,
  levelOptions,
  stateOptions,
  sourceOptions = [],
  sourceLoading = false,
  onFilterChange,
  clearFilters,
}) => {
  const { t } = useTranslation();

  const filterConfigs = [
    {
      field: 'level' as AlarmFilterField,
      title: t('alarms.level'),
      options: levelOptions,
    },
    {
      field: 'state' as AlarmFilterField,
      title: t('alarms.state'),
      options: stateOptions,
    },
  ];

  return (
    <div className={styles.filters}>
      <h3 className="mb-[16px] text-[15px] font-[800]">
        {t('alarms.filterItems')}
      </h3>
      <div>
        {filterConfigs.map(({ field, title, options }) => (
          <div key={field}>
            <Collapse
              title={
                <div className={styles.header}>
                  <span>{title}</span>
                  <ClearOutlined
                    onClick={(event) => {
                      event.stopPropagation();
                      clearFilters(field);
                    }}
                    className={styles.clearIcon}
                  />
                </div>
              }
            >
              <Checkbox.Group
                className={styles.group}
                value={filters[field]}
                onChange={(vals) => onFilterChange(vals as string[], field)}
              >
                <Space direction="vertical">
                  {options.map(({ value, label, color }) => (
                    <Checkbox key={value} value={value}>
                      {color ? (
                        <span
                          className={styles.levelBar}
                          style={{ backgroundColor: color }}
                        />
                      ) : null}
                      {label}
                    </Checkbox>
                  ))}
                </Space>
              </Checkbox.Group>
            </Collapse>
          </div>
        ))}

        {filterSource ? (
          <div>
            <Collapse
              title={
                <div className={styles.header}>
                  <span>{t('alarms.source')}</span>
                  <ClearOutlined
                    onClick={(event) => {
                      event.stopPropagation();
                      clearFilters('alarm_source');
                    }}
                    className={styles.clearIcon}
                  />
                </div>
              }
            >
              <Spin size="small" spinning={sourceLoading}>
                <Checkbox.Group
                  className={styles.group}
                  value={filters.alarm_source}
                  onChange={(vals) =>
                    onFilterChange(vals as string[], 'alarm_source')
                  }
                >
                  <Space direction="vertical">
                    {sourceOptions.map((option) => (
                      <Checkbox key={option.value} value={option.value}>
                        {option.label}
                      </Checkbox>
                    ))}
                  </Space>
                </Checkbox.Group>
              </Spin>
            </Collapse>
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default AlarmFilters;
