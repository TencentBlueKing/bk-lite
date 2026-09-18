'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import { DatePicker, Spin, Input, Select, Button, message } from 'antd';
import {
  SearchOutlined,
  DownloadOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useTranslation } from '@/utils/i18n';
import { useCommon } from '@/app/cmdb/context/common';
import {
  useChangeRecordApi,
  useModelApi,
  useInstanceApi,
} from '@/app/cmdb/api';
import CompactEmptyState from '@/components/compact-empty-state';
import styles from './index.module.scss';
import { AttrFieldType } from '@/app/cmdb/types/assetManage';
import { buildChangeRecordDiffRows } from './changeRecordDiff';
import type { ChangeRecord } from './changeRecordTypes';
import { ChangeRecordTimeline } from './ChangeRecordTimeline';
import { ChangeRecordDetail } from './ChangeRecordDetail';
import {
  DEFAULT_SCENARIOS,
  SCENARIO_COLORS,
  STAT_KEYS,
  getChangeRecordRelationInfo,
} from './changeRecordView';

const { RangePicker } = DatePicker;

const ChangeRecords: React.FC = () => {
  const { t } = useTranslation();
  const changeRecordApi = useChangeRecordApi();
  const modelApi = useModelApi();
  const instanceApi = useInstanceApi();
  const commonContext = useCommon();
  const modelList = commonContext?.modelList || [];

  const searchParams = useSearchParams();
  const modelId: string = searchParams.get('model_id') || '';
  const instUuid: string = searchParams.get('inst_uuid') || '';

  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [records, setRecords] = useState<ChangeRecord[]>([]);
  const [typeEnum, setTypeEnum] = useState<Record<string, string>>({});
  const [scenarioEnum, setScenarioEnum] = useState<Record<string, string>>({});
  const [attrList, setAttrList] = useState<AttrFieldType[]>([]);
  const [currentInstance, setCurrentInstance] = useState<Record<string, any>>(
    {},
  );

  const [scenarioFilters, setScenarioFilters] = useState<string[]>(
    DEFAULT_SCENARIOS,
  );
  const [searchText, setSearchText] = useState('');
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);
  const [operatorFilter, setOperatorFilter] = useState<string | undefined>(
    undefined,
  );
  const [selectedId, setSelectedId] = useState<number | string | null>(null);
  const [detailCollapsed, setDetailCollapsed] = useState(false);

  const fetchRecords = useCallback(
    async (params: any = {}) => {
      setLoading(true);
      try {
        const query: any = {
          model_id: modelId,
          inst_uuid: instUuid,
          ...params,
        };
        const data = await changeRecordApi.getChangeRecords(query);
        const list: ChangeRecord[] = Array.isArray(data) ? data : data?.items || [];
        setRecords(list);
        if (list.length && !selectedId) {
          setSelectedId(list[0].id);
        }
      } finally {
        setLoading(false);
      }
    },
    [modelId, instUuid, changeRecordApi, selectedId],
  );

  useEffect(() => {
    (async () => {
      try {
        const [typeData, scenarioData, attrs, inst] = await Promise.all([
          changeRecordApi.getChangeRecordEnumData(),
          changeRecordApi.getChangeRecordScenarioEnum(),
          modelApi.getModelAttrList(modelId),
          instUuid ? instanceApi.getInstanceDetail(instUuid) : Promise.resolve({}),
        ]);
        setTypeEnum(typeData || {});
        setScenarioEnum(scenarioData || {});
        setAttrList(attrs || []);
        setCurrentInstance(inst || {});
      } catch {
        // ignore — 各项失败不阻塞主列表加载
      }
      fetchRecords();
    })();
     
  }, []);

  const attrFieldMap = useMemo(() => {
    const map: Record<string, AttrFieldType> = {};
    (attrList || []).forEach((attr) => {
      map[attr.attr_id] = attr;
    });
    return map;
  }, [attrList]);

  const operatorOptions = useMemo(() => {
    const names = new Set<string>();
    records.forEach((item) => item.operator && names.add(item.operator));
    return Array.from(names).map((operator) => ({
      value: operator,
      label: operator,
    }));
  }, [records]);

  const filtered = useMemo(() => {
    let list = records;
    if (scenarioFilters.length > 0) {
      list = list.filter((item) => scenarioFilters.includes(item.scenario));
    }
    if (searchText) {
      list = list.filter(
        (item) =>
          (item.message || '').includes(searchText) ||
          (item.operator || '').includes(searchText),
      );
    }
    if (operatorFilter) {
      list = list.filter((item) => item.operator === operatorFilter);
    }
    if (dateRange && (dateRange[0] || dateRange[1])) {
      list = list.filter((item) => {
        const ts = dayjs(item.created_at);
        if (dateRange[0] && ts.isBefore(dayjs(dateRange[0]))) return false;
        if (dateRange[1] && ts.isAfter(dayjs(dateRange[1]))) return false;
        return true;
      });
    }
    return list;
  }, [records, scenarioFilters, searchText, operatorFilter, dateRange]);

  const stats = useMemo(() => {
    const map: Record<string, number> = { all: records.length };
    STAT_KEYS.forEach((key) => (map[key] = 0));
    records.forEach((item) => {
      if (map[item.scenario] !== undefined) map[item.scenario]++;
    });
    return map;
  }, [records]);

  const selectedRecord = useMemo(
    () =>
      detailCollapsed
        ? null
        : filtered.find((item) => item.id === selectedId) || null,
    [filtered, selectedId, detailCollapsed],
  );

  useEffect(() => {
    if (detailCollapsed) return;
    if (filtered.length && !filtered.find((item) => item.id === selectedId)) {
      setSelectedId(filtered[0].id);
    }
  }, [filtered, selectedId, detailCollapsed]);

  const toggleScenario = useCallback((key: string) => {
    if (key === 'all') {
      setScenarioFilters([]);
      return;
    }
    setScenarioFilters((prev) =>
      prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key],
    );
  }, []);

  const removeScenario = useCallback((key: string) => {
    setScenarioFilters((prev) => prev.filter((item) => item !== key));
  }, []);

  const handleExport = async () => {
    try {
      setExporting(true);
      const params: any = { model_id: modelId, inst_uuid: instUuid };
      if (scenarioFilters.length) {
        params.scenarios = scenarioFilters.join(',');
      }
      if (dateRange && dateRange[0]) params.created_at_after = dateRange[0];
      if (dateRange && dateRange[1]) params.created_at_before = dateRange[1];
      if (operatorFilter) params.operator = operatorFilter;
      if (searchText) params.message = searchText;
      const blob = await changeRecordApi.exportChangeRecords(params);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `change_record_${instUuid}_${dayjs().format(
        'YYYYMMDD_HHmmss',
      )}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      message.success(t('OperationLog.exportSuccess'));
    } catch {
      message.error(t('OperationLog.exportFailed'));
    } finally {
      setExporting(false);
    }
  };

  const scenarioLabel = (key: string) =>
    scenarioEnum[key] || t(`OperationLog.scenarioOpts.${key}`) || key;

  const typeLabel = (key: string) =>
    typeEnum[key] || t(`OperationLog.operationOpts.${key}`) || key;

  const showModelName = (id: string) =>
    modelList.find((model: any) => model.model_id === id)?.model_name || id;

  const diffRows = useMemo(
    () => buildChangeRecordDiffRows(selectedRecord, currentInstance, attrFieldMap),
    [selectedRecord, currentInstance, attrFieldMap],
  );
  const relationInfo = useMemo(
    () => getChangeRecordRelationInfo(selectedRecord),
    [selectedRecord],
  );

  const idxInFiltered = selectedRecord
    ? filtered.findIndex((item) => item.id === selectedRecord.id)
    : -1;
  const canPrev = idxInFiltered > 0;
  const canNext = idxInFiltered >= 0 && idxInFiltered < filtered.length - 1;

  return (
    <Spin spinning={loading}>
      <div
        className={`${styles.changeRecords} ${
          detailCollapsed ? styles.collapsed : ''
        }`}
      >
        <div className={styles.timelineCol}>
          <div className={styles.pageTitle}>
            {t('Model.changeRecords')}
            <InfoCircleOutlined className="text-sm text-[var(--color-text-4)]" />
          </div>

          <div className={styles.statsBar}>
            <div className={styles.statCell}>
              <div className={styles.statLabel}>
                {t('Model.changeRecord.allChanges')}
              </div>
              <div className={`${styles.statCount} text-[var(--color-text-1)]`}>
                {stats.all || 0}
              </div>
            </div>
            {STAT_KEYS.map((key) => {
              const colors = SCENARIO_COLORS[key];
              return (
                <div key={key} className={styles.statCell}>
                  <div className={styles.statLabel}>{scenarioLabel(key)}</div>
                  <div className={styles.statCount} style={{ color: colors.dot }}>
                    {stats[key] || 0}
                  </div>
                </div>
              );
            })}
          </div>

          <div className={styles.filterChips}>
            <button
              className={`${styles.chip} ${
                scenarioFilters.length === 0 ? styles.chipActive : ''
              }`}
              onClick={() => toggleScenario('all')}
            >
              {t('Model.changeRecord.allFilter')}
            </button>
            {STAT_KEYS.map((key) => {
              const colors = SCENARIO_COLORS[key];
              const isActive = scenarioFilters.includes(key);
              return (
                <button
                  key={key}
                  className={`${styles.chip} ${isActive ? styles.chipActive : ''}`}
                  onClick={() => toggleScenario(key)}
                >
                  <span
                    className={styles.chipDot}
                    style={{ background: colors.dot }}
                  />
                  {scenarioLabel(key)}
                  {isActive && (
                    <span
                      className={styles.chipClose}
                      onClick={(event) => {
                        event.stopPropagation();
                        removeScenario(key);
                      }}
                    >
                      ✕
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          <div className={styles.filterRow}>
            <Input
              size="small"
              prefix={<SearchOutlined className="text-[#B2BDCC]" />}
              placeholder={t('Model.changeRecord.searchPlaceholder')}
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              allowClear
              className="min-w-[140px] flex-1"
            />
            <RangePicker
              size="small"
              className="w-60"
              onChange={(_, dates) => {
                const range: [string, string] | null =
                  dates && (dates[0] || dates[1])
                    ? [dates[0] || '', dates[1] || '']
                    : null;
                setDateRange(range);
              }}
            />
            <Select
              size="small"
              allowClear
              placeholder={t('Model.changeRecord.operatorPlaceholder')}
              className="w-[110px]"
              options={operatorOptions}
              value={operatorFilter}
              onChange={(value) => setOperatorFilter(value)}
            />
            <Button
              size="small"
              icon={<DownloadOutlined />}
              loading={exporting}
              onClick={handleExport}
            />
          </div>

          {filtered.length === 0 && !loading ? (
            <CompactEmptyState
              className="mt-[60px]"
              description={t('common.noData')}
            />
          ) : (
            <ChangeRecordTimeline
              records={filtered}
              selectedId={detailCollapsed ? null : selectedId}
              onSelect={(id) => {
                setSelectedId(id);
                setDetailCollapsed(false);
              }}
              scenarioLabel={scenarioLabel}
              typeLabel={typeLabel}
              showModelName={showModelName}
            />
          )}
        </div>

        {!detailCollapsed && (
          <div className={styles.detailCol}>
            <ChangeRecordDetail
              record={selectedRecord}
              diffRows={diffRows}
              relationInfo={relationInfo}
              scenarioLabel={scenarioLabel}
              showModelName={showModelName}
              canPrev={canPrev}
              canNext={canNext}
              onPrev={() => {
                if (canPrev) {
                  setSelectedId(filtered[idxInFiltered - 1].id);
                  setDetailCollapsed(false);
                }
              }}
              onNext={() => {
                if (canNext) {
                  setSelectedId(filtered[idxInFiltered + 1].id);
                  setDetailCollapsed(false);
                }
              }}
              onClose={() => setDetailCollapsed(true)}
            />
          </div>
        )}
      </div>
    </Spin>
  );
};

export default ChangeRecords;
