import React, { useEffect, useState } from 'react';
import Collapse from '@/components/collapse';
import alertStyle from './index.module.scss';
import { Checkbox, Select, Space, Spin, Tooltip } from 'antd';
import { ClearOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { FiltersConfig } from '@/app/alarm/types/alarms';
import { useSourceApi } from '@/app/alarm/api/integration';
import { AlertSourceOption } from '@/app/alarm/types/integration';
import { useCommon } from '@/app/alarm/context/common';
import { normalizeRuleTags } from '@/app/alarm/utils/multivalueRules';

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
  const { getAlertSourceOptions, getPushSourceIdOptions } = useSourceApi();
  const { levelList, levelMap } = useCommon();
  const [sourceOptions, setSourceOptions] = useState<AlertSourceOption[]>([]);
  const [loadingSources, setLoadingSources] = useState(false);
  const [pushCatalog, setPushCatalog] = useState<string[]>([]);
  const [loadingPushCatalog, setLoadingPushCatalog] = useState(false);

  useEffect(() => {
    if (!filterSource) return;
    const fetchSources = async () => {
      setLoadingSources(true);
      try {
        const res = await getAlertSourceOptions();
        if (res) setSourceOptions(res);
      } catch {
        setSourceOptions([]);
      } finally {
        setLoadingSources(false);
      }
    };
    void fetchSources();
  }, [filterSource]);

  useEffect(() => {
    const fetchPushCatalog = async () => {
      setLoadingPushCatalog(true);
      try {
        const rows = await getPushSourceIdOptions();
        setPushCatalog(Array.isArray(rows) ? rows.filter((item): item is string => typeof item === 'string' && !!item.trim()) : []);
      } catch {
        setPushCatalog([]);
      } finally {
        setLoadingPushCatalog(false);
      }
    };
    void fetchPushCatalog();
  }, []);

  const pushCatalogSet = new Set(pushCatalog);
  const selectedPush = filters.push_source_ids.filter((item) => pushCatalogSet.has(item));
  const manualPush = filters.push_source_ids.filter((item) => !pushCatalogSet.has(item));
  const publishPush = (next: string[]) => onFilterChange(normalizeRuleTags(next).slice(0, 50), 'push_source_ids');
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
                  onChange={(vals) => onFilterChange(vals as string[], 'alarm_source')}
                >
                  <Space direction="vertical">
                    {sourceOptions.map((source) => (
                      <Checkbox key={source.name} value={source.name}>
                        {source.name}
                      </Checkbox>
                    ))}
                  </Space>
                </Checkbox.Group>
              </Spin>
            </Collapse>
          </div>
        )}
        <div className={alertStyle.item}>
          <Collapse
            title={
              <div className={alertStyle.header}>
                <span>{t('alarmCommon.ruleFields.push_source_ids')}</span>
                <ClearOutlined
                  onClick={(e) => {
                    e.stopPropagation();
                    clearFilters('push_source_ids');
                  }}
                  className={alertStyle.clearIcon}
                />
              </div>
            }
          >
            <Spin size="small" spinning={loadingPushCatalog}>
              <Checkbox.Group
                className={alertStyle.group}
                value={selectedPush}
                onChange={(vals) => publishPush([...(vals as string[]), ...manualPush])}
              >
                <Space direction="vertical">
                  {pushCatalog.map((sourceId) => (
                    <Checkbox key={sourceId} value={sourceId}>
                      {sourceId}
                    </Checkbox>
                  ))}
                </Space>
              </Checkbox.Group>
            </Spin>
          </Collapse>
          <Tooltip title={t('alarmCommon.pushSourceCustomHint')} mouseEnterDelay={0}>
            <div className="mt-2">
              <Select<string[]>
                className="w-full"
                mode="tags"
                open={false}
                suffixIcon={null}
                options={[]}
                aria-label={t('alarmCommon.pushSourceInput')}
                placeholder={t('alarmCommon.pushSourceCustomPlaceholder')}
                value={manualPush}
                maxCount={50 - selectedPush.length}
                maxLength={256}
                onChange={(next) => {
                  const tags = normalizeRuleTags(next);
                  publishPush([
                    ...selectedPush,
                    ...tags.filter((item) => pushCatalogSet.has(item)),
                    ...tags.filter((item) => !pushCatalogSet.has(item)),
                  ]);
                }}
              />
            </div>
          </Tooltip>
        </div>
      </div>
    </div>
  );
};

export default AlarmFilters;
