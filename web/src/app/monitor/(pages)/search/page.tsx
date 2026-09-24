'use client';
import './register-search-pilot';
import React, { useEffect, useState, useRef } from 'react';
import { Segmented } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import {
  AppstoreOutlined,
  BarsOutlined
} from '@ant-design/icons';
import useApiClient from '@/utils/request';
import TimeSelector from '@/components/time-selector';
import { useTranslation } from '@/utils/i18n';
import { TimeSelectorDefaultValue, TimeValuesProps } from '@/app/monitor/types';
import { Dayjs } from 'dayjs';
import { useSearchParams } from 'next/navigation';
import {
  SearchPayload,
  QueryPanelRef,
  ChartItem
} from '@/app/monitor/types/search';
import {
  renderChart,
} from '@/app/monitor/utils/common';
import { attachGapIntervals } from '@/app/monitor/utils/gapIntervals';
import dayjs from 'dayjs';
import QueryPanel from './queryPanel';
import SearchResultCard from './searchResultCard';
import { publishSearchSnapshot } from './search.pilot';
import {
  applySearchPresentationToAll,
  emptySearchChartPresentation,
  seedSearchChartPresentation,
  type SearchChartPresentation
} from './searchChartPresentation';
import {
  buildSearchQueryParams,
  expandSearchCards,
  getMetricsMapKey,
  resolveMetricSelection
} from './searchQueryLogic';
import { parseSearchTimeQueryParams } from '@/app/monitor/utils/searchTimeQuery';

const SEARCH_LAYOUT_STORAGE_KEY = 'bk-lite.monitor.search.layoutMode';
const SEARCH_DEFAULT_REFRESH_MS = 60_000;

const readStoredLayoutMode = (): 'single' | 'double' | null => {
  if (typeof window === 'undefined') return null;
  const stored = window.localStorage.getItem(SEARCH_LAYOUT_STORAGE_KEY);
  return stored === 'single' || stored === 'double' ? stored : null;
};

const SearchView: React.FC = () => {
  const { post } = useApiClient();
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const parsedSearchTime = parseSearchTimeQueryParams(searchParams);
  const queryPanelRef = useRef<QueryPanelRef>(null);
  const [layoutMode, setLayoutMode] = useState<'single' | 'double'>('single');
  const [timeValues, setTimeValues] = useState<TimeValuesProps>(
    parsedSearchTime.timeValues
  );
  const [timeDefaultValue, setTimeDefaultValue] =
    useState<TimeSelectorDefaultValue>(() => ({
      selectValue: parsedSearchTime.selectValue,
      rangePickerVaule:
        parsedSearchTime.rangeStart != null && parsedSearchTime.rangeEnd != null
          ? [dayjs(parsedSearchTime.rangeStart), dayjs(parsedSearchTime.rangeEnd)]
          : null
    }));
  const [chartItems, setChartItems] = useState<ChartItem[]>([]);
  const [presentationByGroupId, setPresentationByGroupId] = useState<
    Record<string, SearchChartPresentation>
  >({});
  const [frequence, setFrequence] = useState<number>(SEARCH_DEFAULT_REFRESH_MS);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const searchAbortControllerRef = useRef<AbortController | null>(null);
  const searchRequestIdRef = useRef<number>(0);
  const lastSearchPayloadRef = useRef<SearchPayload | null>(null);

  useEffect(() => {
    const payload = queryPanelRef.current?.getSearchPayload() || lastSearchPayloadRef.current;
    publishSearchSnapshot({
      payload,
      charts: chartItems,
    });
    return () => publishSearchSnapshot(null);
  }, [chartItems, timeValues]);

  useEffect(() => {
    const stored = readStoredLayoutMode();
    if (stored) setLayoutMode(stored);
  }, []);

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
      (g) => g.instanceIds.length > 0
    );
    const cards = expandSearchCards(validGroups);
    if (!cards.length) return;
    setPresentationByGroupId((prev) =>
      seedSearchChartPresentation(
        prev,
        cards.map((card) => ({
          id: card.cardId,
          viewMode: card.group.viewMode,
          tableKind: card.group.tableKind
        }))
      )
    );
    searchAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    searchAbortControllerRef.current = abortController;
    const currentRequestId = ++searchRequestIdRef.current;
    const initialChartItems: ChartItem[] = cards.map((card) => {
      const dataKey = getMetricsMapKey(card.group.object, card.group.plugin);
      const metrics = payload.metricsMap[dataKey] || [];
      const metricItem = resolveMetricSelection(metrics, card.metricId);
      const objectItem = payload.objectsMap[String(card.group.object)];
      return {
        cardId: card.cardId,
        groupId: card.group.id,
        groupName: card.group.name,
        metric: metricItem,
        data: [],
        unit: '',
        loading: true,
        duration: 0,
        objectName: objectItem?.display_name || '',
        aggregation: card.group.aggregation || 'AVG'
      };
    });
    if (type !== 'timer') {
      setChartItems(initialChartItems);
    }
    const requests = cards.map(async (card) => {
      const startTime = Date.now();
      const patchCard = (updates: Partial<ChartItem>) => {
        setChartItems((prev) =>
          prev.map((item) =>
            item.cardId === card.cardId ? { ...item, ...updates } : item
          )
        );
      };
      try {
        const dataKey = getMetricsMapKey(card.group.object, card.group.plugin);
        const metrics = payload.metricsMap[dataKey] || [];
        const instances = payload.instancesMap[dataKey] || [];
        const params = buildSearchQueryParams({
          group: card.group,
          metrics,
          instances,
          timeRange: _timeRange,
          metricId: card.metricId
        });
        // 实例列表尚未对齐时 selectedInstances 可能为空；勿发受控查询以免触发 instance_ids 校验刷屏。
        if (!Array.isArray(params.instance_ids) || params.instance_ids.length === 0) {
          if (currentRequestId !== searchRequestIdRef.current) return;
          patchCard({ data: [], loading: false, duration: Date.now() - startTime });
          return;
        }
        const responseData = await post(
          '/monitor/api/metrics_instance/query_by_metric_range/',
          params,
          {
            signal: abortController.signal
          }
        );
        if (currentRequestId !== searchRequestIdRef.current) return;
        const data = responseData.data?.result || [];
        const displayUnit = responseData.data?.unit || '';
        const targetMetric = resolveMetricSelection(metrics, card.metricId);
        const list = instances
          .filter((item) => card.group.instanceIds.includes(item.instance_id))
          .map((item) => {
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
        const chartData = attachGapIntervals(
          renderChart(data, list),
          responseData.data?.gaps || []
        );
        patchCard({
          data: chartData,
          unit: displayUnit,
          loading: false,
          duration: Date.now() - startTime
        });
      } catch {
        if (currentRequestId !== searchRequestIdRef.current) return;
        patchCard({ loading: false, duration: Date.now() - startTime });
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

  const updatePresentation = (
    cardId: string,
    groupId: string,
    next: SearchChartPresentation
  ) => {
    setPresentationByGroupId((prev) => ({ ...prev, [cardId]: next }));
    queryPanelRef.current?.updateGroupPresentation(groupId, {
      viewMode: next.view,
      tableKind: next.tableKind
    });
  };

  const applyPresentationToAll = (source: SearchChartPresentation) => {
    const cardIds = chartItems.map((item) => item.cardId || item.groupId);
    setPresentationByGroupId((prev) =>
      applySearchPresentationToAll(prev, cardIds, source)
    );
    [...new Set(chartItems.map((item) => item.groupId))].forEach((groupId) => {
      queryPanelRef.current?.updateGroupPresentation(groupId, {
        viewMode: source.view,
        tableKind: source.tableKind
      });
    });
  };

  return (
    <div
      className="flex h-full min-h-0 min-w-0 w-full"
      style={{ backgroundColor: 'var(--color-bg-1)' }}
    >
      {/* 左侧查询面板 */}
      <QueryPanel ref={queryPanelRef} onSearch={handleSearchFromPanel} />
      {/* 右侧内容区 */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* 顶部工具栏 */}
        <div className="flex items-center justify-end p-5 pb-0">
          <div className="flex items-center gap-4">
            <TimeSelector
              defaultValue={timeDefaultValue}
              frequenceValue={frequence}
              onChange={onTimeChange}
              onFrequenceChange={onFrequenceChange}
              onRefresh={onRefresh}
            />
            <Segmented
              value={layoutMode}
              onChange={(value) => {
                const next = value as 'single' | 'double';
                setLayoutMode(next);
                window.localStorage.setItem(SEARCH_LAYOUT_STORAGE_KEY, next);
              }}
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
                <SearchResultCard
                  key={item.cardId || item.groupId}
                  item={item}
                  layoutMode={layoutMode}
                  presentation={
                    presentationByGroupId[item.cardId || item.groupId] ||
                    emptySearchChartPresentation()
                  }
                  showApplyAll={chartItems.length > 1}
                  onPresentationChange={(next) =>
                    updatePresentation(
                      item.cardId || item.groupId,
                      item.groupId,
                      next
                    )
                  }
                  onApplyAll={() =>
                    applyPresentationToAll(
                      presentationByGroupId[item.cardId || item.groupId] ||
                        emptySearchChartPresentation()
                    )
                  }
                  onXRangeChange={onXRangeChange}
                />
              ))}
            </div>
          ) : (
            <div className="flex items-center justify-center h-full">
              <CompactEmptyState description={t('monitor.search.noData')} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SearchView;
