import React, { useState, useEffect } from 'react';
import Collapse from '@/components/collapse';
import alertStyle from './index.module.scss';
import { Checkbox, Space, Spin } from 'antd';
import { ClearOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { FiltersConfig } from '@/app/alarm/types/alarms';
import { useSourceApi } from '@/app/alarm/api/integration';
import { AlertSourceOption } from '@/app/alarm/types/integration';
import { useCommon } from '@/app/alarm/context/common';

interface Props {
  filters: FiltersConfig;
  filterSource?: boolean;
  stateOptions: { value: string; label: string }[];
  onFilterChange: (vals: string[], field: keyof FiltersConfig) => void;
  clearFilters: (field: keyof FiltersConfig) => void;
}

const AlarmFilters: React.FC<Props> = ({
  filters,
  filterSource = true,
  stateOptions,
  onFilterChange,
  clearFilters,
}) => {
  const { t } = useTranslation();
  const { getAlertSourceOptions } = useSourceApi();
  const { levelList, levelMap } = useCommon();
  const [sourceOptions, setSourcesOptions] = useState<AlertSourceOption[]>([]);
  const [loadingSources, setLoadingSources] = useState<boolean>(false);

  useEffect(() => {
    if (!filterSource) return;
    const fetchSources = async () => {
      setLoadingSources(true);
      try {
        const res = await getAlertSourceOptions();
        if (res) setSourcesOptions(res);
      } catch (err) {
        console.error(err);
      } finally {
        setLoadingSources(false);
      }
    };
    fetchSources();
  }, [filterSource]);

  const filterConfigs = [
    {
      field: 'level' as keyof FiltersConfig,
      title: t('alarms.level'),
      options: levelList,
    },
    {
      field: 'state' as keyof FiltersConfig,
      title: t('alarms.state'),
      options: stateOptions,
    },
  ];

  return (
    <div className={alertStyle.filters}>
      <h3 className="font-[800] mb-[16px] text-[15px]">
        {t('alarms.filterItems')}
      </h3>
      <div className={alertStyle.container}>
        {filterConfigs.map(({ field, title, options }) => (
          <div key={field} className={alertStyle.item}>
            <Collapse
              title={
                <div className={alertStyle.header}>
                  <span>{title}</span>
                  <ClearOutlined
                    onClick={(e) => {
                      e.stopPropagation();
                      clearFilters(field);
                    }}
                    className={alertStyle.clearIcon}
                  />
                </div>
              }
            >
              <Checkbox.Group
                className={alertStyle.group}
                value={filters[field]}
                onChange={(vals) => onFilterChange(vals as string[], field)}
              >
                <Space direction="vertical">
                  {options.map(({ value, label }) => (
                    <Checkbox key={value} value={value}>
                      {levelMap[value] && (
                        <span
                          className={alertStyle.levelBar}
                          style={{
                            backgroundColor: `${levelMap[value]}`,
                          }}
                        ></span>
                      )}
                      {label}
                    </Checkbox>
                  ))}
                </Space>
              </Checkbox.Group>
            </Collapse>
          </div>
        ))}
        {filterSource && (
          <div className={alertStyle.item}>
            <Collapse
              title={
                <div className={alertStyle.header}>
                  <span>{t('alarms.source')}</span>
                  <ClearOutlined
                    onClick={(e) => {
                      e.stopPropagation();
                      clearFilters('alarm_source');
                    }}
                    className={alertStyle.clearIcon}
                  />
                </div>
              }
            >
              <Spin size="small" spinning={loadingSources}>
                <Checkbox.Group
                  className={alertStyle.group}
                  value={filters.alarm_source}
                  onChange={(vals) =>
                    onFilterChange(vals as string[], 'alarm_source')
                  }
                >
                  <Space direction="vertical">
                    {sourceOptions.map((o: AlertSourceOption) => (
                      <Checkbox key={o.name} value={o.name}>
                        {o.name}
                      </Checkbox>
                    ))}
                  </Space>
                </Checkbox.Group>
              </Spin>
            </Collapse>
          </div>
        )}
      </div>
    </div>
  );
};

export default AlarmFilters;
