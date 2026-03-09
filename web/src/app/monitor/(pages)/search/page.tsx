'use client';
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Tooltip, Card, Empty, Segmented } from 'antd';
import {
  AppstoreOutlined,
  BarsOutlined,
  QuestionCircleFilled
} from '@ant-design/icons';
import useApiClient from '@/utils/request';
import TimeSelector from '@/components/time-selector';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';
import LineChart from '@/app/monitor/components/charts/lineChart';
import { TimeSelectorDefaultValue, TimeValuesProps } from '@/app/monitor/types';
import { Dayjs } from 'dayjs';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';
import {
  SearchParams,
  SearchPayload,
  QueryGroup,
  QueryPanelRef,
  ChartItem
} from '@/app/monitor/types/search';
import {
  mergeViewQueryKeyValues,
  renderChart,
  getRecentTimeRange
} from '@/app/monitor/utils/common';
import dayjs from 'dayjs';
import QueryPanel from './queryPanel';

const SearchView: React.FC = () => {
  const { get } = useApiClient();
  const { t } = useTranslation();
  const { findUnitNameById } = useUnitTransform();
  const queryPanelRef = useRef<QueryPanelRef>(null);
  const [layoutMode, setLayoutMode] = useState<'single' | 'double'>('single');
  const [timeValues, setTimeValues] = useState<TimeValuesProps>({
    timeRange: [],
    originValue: 15
  });
  const [timeDefaultValue, setTimeDefaultValue] =
    useState<TimeSelectorDefaultValue>({
      selectValue: 15,
      rangePickerVaule: null
    });
  const [chartItems, setChartItems] = useState<ChartItem[]>([]);
  const [frequence, setFrequence] = useState<number>(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const searchAbortControllerRef = useRef<AbortController | null>(null);
  const searchRequestIdRef = useRef<number>(0);
  const lastSearchPayloadRef = useRef<SearchPayload | null>(null);

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  useEffect(() => {
    return () => {
      clearTimer();
      searchAbortControllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!frequence) {
      clearTimer();
      return;
    }
    timerRef.current = setInterval(() => {
      handleSearch('timer');
    }, frequence);
    return () => {
      clearTimer();
    };
  }, [frequence, timeValues]);

  const handleSearchFromPanel = (payload: SearchPayload) => {
    lastSearchPayloadRef.current = payload;
    executeSearch('refresh', timeValues, payload);
  };

  const getParams = (
    group: QueryGroup,
    _timeRange: TimeValuesProps,
    payload: SearchPayload
  ): SearchParams => {
    const metrics = payload.metricsMap[String(group.object)] || [];
    const instances = payload.instancesMap[String(group.object)] || [];
    const metricItem = metrics.find((item) => item.name === group.metric);
    const _query: string = metricItem?.query || '';
    const queryValues: string[][] = instances
      .filter((item) => group.instanceIds.includes(item.instance_id))
      .map((item) => item.instance_id_values);
    const querykeys: string[] = metricItem?.instance_id_keys || [];
    const queryList = queryValues.map((values) => ({
      keys: querykeys,
      values
    }));
    const params: SearchParams = {
      query: '',
      source_unit: metricItem?.unit || ''
    };
    const recentTimeRange = getRecentTimeRange(_timeRange);
    const startTime = recentTimeRange.at(0);
    const endTime = recentTimeRange.at(1);
    if (startTime && endTime) {
      const MAX_POINTS = 100;
      const DEFAULT_STEP = 360;
      params.start = startTime;
      params.end = endTime;
      params.step = Math.max(
        Math.ceil(
          (params.end / MAX_POINTS - params.start / MAX_POINTS) / DEFAULT_STEP
        ),
        1
      );
    }
    let query = '';
    if (group.instanceIds.length) {
      query += mergeViewQueryKeyValues(queryList);
    }
    if (group.conditions.length) {
      const conditionQueries = group.conditions
        .map((condition) => {
          if (condition.label && condition.condition && condition.value) {
            return `${condition.label}${condition.condition}"${condition.value}"`;
          }
          return '';
        })
        .filter(Boolean);
      if (conditionQueries.length) {
        if (query) query += ',';
        query += conditionQueries.join(',');
      }
    }
    let finalQuery = _query.replace(/__\$labels__/g, query);
    if (group.aggregation && group.aggregation !== 'AVG') {
      const aggFunc = group.aggregation.toLowerCase();
      finalQuery = `${aggFunc}(${finalQuery})`;
    }
    params.query = finalQuery;
    return params;
  };

  const handleSearch = (type: string, _timeRange = timeValues) => {
    const payload = lastSearchPayloadRef.current;
    if (!payload) return;
    executeSearch(type, _timeRange, payload);
  };

  const executeSearch = async (
    type: string,
    _timeRange: TimeValuesProps,
    payload: SearchPayload
  ) => {
    const validGroups = payload.queryGroups.filter(
      (g) => g.metric && g.instanceIds.length > 0
    );
    if (!validGroups?.length) return;
    searchAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    searchAbortControllerRef.current = abortController;
    const currentRequestId = ++searchRequestIdRef.current;
    const initialChartItems: ChartItem[] = validGroups.map((group) => {
      const metrics = payload.metricsMap[String(group.object)] || [];
      const metricItem = metrics.find((m) => m.name === group.metric) || null;
      const objectItem = payload.objectsMap[String(group.object)];
      return {
        groupId: group.id,
        groupName: group.name,
        metric: metricItem,
        data: [],
        unit: '',
        loading: true,
        duration: 0,
        objectName: objectItem?.display_name || '',
        aggregation: group.aggregation || 'AVG'
      };
    });
    if (type !== 'timer') {
      setChartItems(initialChartItems);
    }
    const requests = validGroups.map(async (group, index) => {
      const startTime = Date.now();
      try {
        const params = getParams(group, _timeRange, payload);
        const responseData = await get(
          '/monitor/api/metrics_instance/query_range/',
          {
            params,
            signal: abortController.signal
          }
        );
        if (currentRequestId !== searchRequestIdRef.current) return;
        const data = responseData.data?.result || [];
        const displayUnit = responseData.data?.unit || '';
        const metrics = payload.metricsMap[String(group.object)] || [];
        const instances = payload.instancesMap[String(group.object)] || [];
        const list = instances
          .filter((item) => group.instanceIds.includes(item.instance_id))
          .map((item) => {
            const targetMetric = metrics.find((m) => m.name === group.metric);
            return {
              instance_id_values: item.instance_id_values,
              instance_name: item.instance_name,
              instance_id: item.instance_id,
              instance_id_keys: targetMetric?.instance_id_keys || [],
              dimensions: targetMetric?.dimensions || [],
              title: targetMetric?.display_name || '--',
              showInstName: true
            };
          });
        const chartData = renderChart(data, list);
        const duration = Date.now() - startTime;
        setChartItems((prev) =>
          prev.map((item, i) => {
            if (i === index) {
              item.data = chartData;
              item.unit = displayUnit;
              item.loading = false;
              item.duration = duration;
            }
            return item;
          })
        );
      } catch {
        const duration = Date.now() - startTime;
        setChartItems((prev) =>
          prev.map((item, i) =>
            i === index ? { ...item, loading: false, duration } : item
          )
        );
      }
    });
    await Promise.all(requests);
  };

  const onTimeChange = (val: number[], originValue: number | null) => {
    const timeRange = { timeRange: val, originValue };
    setTimeValues(timeRange);
    handleSearch('refresh', timeRange);
  };

  const onFrequenceChange = (val: number) => {
    setFrequence(val);
  };

  const onRefresh = () => {
    handleSearch('refresh');
  };

  const onXRangeChange = (arr: [Dayjs, Dayjs]) => {
    setTimeDefaultValue((pre) => ({
      ...pre,
      rangePickerVaule: arr,
      selectValue: 0
    }));
    const _times = arr.map((item) => dayjs(item).valueOf());
    const timeRange = { timeRange: _times, originValue: 0 };
    setTimeValues(timeRange);
    handleSearch('refresh', timeRange);
  };

  const getUnit = useCallback(
    (unit: string) => {
      const unitName = findUnitNameById(unit);
      return unitName ? `（${unitName}）` : '';
    },
    [findUnitNameById]
  );

  return (
    <div
      className="flex h-full"
      style={{ backgroundColor: 'var(--color-bg-1)' }}
    >
      {/* 左侧查询面板 */}
      <QueryPanel ref={queryPanelRef} onSearch={handleSearchFromPanel} />
      {/* 右侧内容区 */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* 顶部工具栏 */}
        <div className="flex items-center justify-end p-5 pb-0">
          <div className="flex items-center gap-4">
            <TimeSelector
              defaultValue={timeDefaultValue}
              onChange={onTimeChange}
              onFrequenceChange={onFrequenceChange}
              onRefresh={onRefresh}
            />
            <Segmented
              value={layoutMode}
              onChange={(value) => setLayoutMode(value as 'single' | 'double')}
              options={[
                {
                  value: 'single',
                  title: t('monitor.search.singleColumn'),
                  icon: <BarsOutlined />
                },
                {
                  value: 'double',
                  title: t('monitor.search.doubleColumn'),
                  icon: <AppstoreOutlined />
                }
              ]}
            />
          </div>
        </div>
        {/* 图表列表 - 可滚动区域 */}
        <div className="flex-1 overflow-y-auto p-5">
          {chartItems.length > 0 ? (
            <div
              className={`grid gap-4 ${
                layoutMode === 'double' ? 'grid-cols-2' : 'grid-cols-1'
              }`}
            >
              {chartItems.map((item) => (
                <Card
                  key={item.groupId}
                  size="small"
                  style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}
                  title={
                    <div className="flex items-center">
                      <EllipsisWithTooltip
                        text={`${item.aggregation}(${item.objectName}-${item.metric?.display_name || '--'})`}
                        className="font-medium truncate max-w-[calc(100%-150px)]"
                      />
                      <span className="font-medium flex-shrink-0">
                        <span className="text-[var(--color-text-3)] text-[12px]">
                          {getUnit(item.unit)}
                        </span>
                        {item.metric?.display_description && (
                          <Tooltip title={item.metric.display_description}>
                            <QuestionCircleFilled
                              className={`cursor-help text-xs align-super ${getUnit(item.unit) ? 'ml-[-6px]' : ''} text-[var(--color-text-3)]`}
                            />
                          </Tooltip>
                        )}
                      </span>
                      {!item.loading && item.duration > 0 && (
                        <span className="text-xs text-[var(--color-text-3)] font-normal flex-shrink-0 whitespace-nowrap ml-[10px]">
                          {t('monitor.search.duration')} {item.duration}
                          {t('monitor.search.ms')}
                        </span>
                      )}
                    </div>
                  }
                  loading={item.loading}
                  styles={{
                    body: { padding: '12px' }
                  }}
                >
                  <div
                    className={
                      layoutMode === 'double' ? 'h-[220px]' : 'h-[280px]'
                    }
                  >
                    <LineChart
                      metric={item.metric || undefined}
                      data={item.data}
                      unit={item.unit}
                      showDimensionTable={layoutMode === 'single'}
                      key={layoutMode}
                      syncId="monitor-search-charts"
                      onXRangeChange={onXRangeChange}
                    />
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <div className="flex items-center justify-center h-full">
              <Empty description={t('monitor.search.noData')} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SearchView;
