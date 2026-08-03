'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Spin, Select, Segmented } from 'antd';
import TimeSelector from '@/components/time-selector';
import Collapse from '@/components/collapse';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import {
  TableDataItem,
  TimeSelectorDefaultValue,
  TimeValuesProps,
  GroupInfo,
  MetricItem,
  IndexViewItem,
} from '@/app/monitor/types';
import { ViewModalProps } from '@/app/monitor/types/view';
import { SearchParams } from '@/app/monitor/types/search';
import { useTranslation } from '@/utils/i18n';
import {
  mergeViewQueryKeyValues,
  renderChart,
} from '@/app/monitor/utils/common';
import { calculateQueryStep } from '@/app/monitor/utils/queryStep';
import { attachGapIntervals, buildGapDetectionParams } from '@/app/monitor/utils/gapIntervals';
import dayjs, { Dayjs } from 'dayjs';
import { INIT_VIEW_MODAL_FORM } from '@/app/monitor/constants/view';
import LazyMetricItem from '@/app/monitor/components/metric-views/lazyMetricItem';
import { createMetricQueryWindow } from '@/app/monitor/components/metric-views/queryWindow';
import { useMetricSelectOptions } from '@/app/monitor/components/metricSelectOptions';
import {
  buildHostProcessLabelPairs,
  isHostMonitorObject,
  isHostProcessMetricsTab,
  resolveHostProcessMetricsTarget,
  resolveProcessNameFromInstance,
  withHostProcessMetricsTab
} from '@/app/monitor/dashboards/objects/host/host-process-metrics-tab';

const MonitorView: React.FC<ViewModalProps> = ({
  monitorObject,
  monitorName,
  plugins,
  form = INIT_VIEW_MODAL_FORM,
}) => {
  const { isLoading } = useApiClient();
  const { get } = useApiClient();
  const { getMetricsGroup, getMonitorMetrics, getMonitorObject, getMonitorPlugin, getInstanceList } =
    useMonitorApi();
  const { t } = useTranslation();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [metricId, setMetricId] = useState<number | null>();
  const [timeValues, setTimeValues] = useState<TimeValuesProps>({
    timeRange: [],
    originValue: 15,
  });
  const [activeQueryWindow, setActiveQueryWindow] = useState(() =>
    createMetricQueryWindow({ timeRange: [], originValue: 15 })
  );
  const activeQueryWindowRef = useRef(activeQueryWindow);
  const [timeDefaultValue, setTimeDefaultValue] =
    useState<TimeSelectorDefaultValue>({
      selectValue: 15,
      rangePickerVaule: null,
    });
  const [frequence, setFrequence] = useState<number>(0);
  const [metricData, setMetricData] = useState<IndexViewItem[]>([]);
  const [originMetricData, setOriginMetricData] = useState<IndexViewItem[]>([]);
  const [activeTab, setActiveTab] = useState<string>('');
  const [tabOptions, setTabOptions] = useState(plugins);
  const [processObjectId, setProcessObjectId] = useState('');
  const [processPluginId, setProcessPluginId] = useState('');
  const [processFilterNames, setProcessFilterNames] = useState<string[]>([]);
  const [processFilterOptions, setProcessFilterOptions] = useState<
    { label: string; value: string }[]
  >([]);
  const [processFilterLoading, setProcessFilterLoading] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const metricSelect = useMetricSelectOptions(originMetricData);
  const [loadedMetricIds, setLoadedMetricIds] = useState<Set<number>>(
    new Set()
  );
  const [loadingMetricIds, setLoadingMetricIds] = useState<Set<number>>(
    new Set()
  );
  const [resetCounter, setResetCounter] = useState<number>(0);
  const [needsRefreshOnExpand, setNeedsRefreshOnExpand] =
    useState<boolean>(false);

  const [cancelledMetricIds, setCancelledMetricIds] = useState<Set<number>>(
    new Set()
  );
  // 跟踪当前可视区域内的指标
  const [visibleMetricIds, setVisibleMetricIds] = useState<Set<number>>(
    new Set()
  );

  // 请求并发控制：与指标详情页一致，排队而非取消最早请求。
  const MAX_CONCURRENT_REQUESTS = 4;
  const activeRequestsRef = useRef<Map<number, AbortController>>(new Map());
  const requestGenerationRef = useRef(0);
  const visibleMetricIdsRef = useRef<Set<number>>(new Set());
  const metricDataRef = useRef<IndexViewItem[]>([]);

  visibleMetricIdsRef.current = visibleMetricIds;
  metricDataRef.current = metricData;

  const isProcessMetricsView = isHostProcessMetricsTab(activeTab);
  const hostLogicalId = String(form?.instance_id_values?.[0] || '').trim();

  const snapshotActiveQueryWindow = () => {
    const nextQueryWindow = createMetricQueryWindow(timeValues);
    activeQueryWindowRef.current = nextQueryWindow;
    setActiveQueryWindow(nextQueryWindow);
  };

  const cancelAllRequests = () => {
    const cancelledIds = Array.from(activeRequestsRef.current.keys());

    activeRequestsRef.current.forEach((abortController) => {
      abortController.abort();
    });
    activeRequestsRef.current.clear();
    requestGenerationRef.current += 1;

    setCancelledMetricIds((prev) => {
      const newSet = new Set(prev);
      cancelledIds.forEach((id) => newSet.add(id));
      return newSet;
    });

    setLoadingMetricIds(new Set());
  };

  useEffect(() => {
    if (isLoading) {
      return;
    }
    if (!form?.instance_id_values.length) {
      return;
    }

    let active = true;
    const bootstrap = async () => {
      let nextOptions = plugins;
      let nextProcessObjectId = '';
      let nextProcessPluginId = '';
      if (isHostMonitorObject(monitorName)) {
        const target = await resolveHostProcessMetricsTarget({
          getMonitorObject,
          getMonitorPlugin
        });
        if (target) {
          nextProcessObjectId = target.processObjectId;
          nextProcessPluginId = target.processPluginId;
          nextOptions = withHostProcessMetricsTab(
            plugins,
            true,
            target.processPluginLabel
          );
        }
      }
      if (!active) return;
      setProcessObjectId(nextProcessObjectId);
      setProcessPluginId(nextProcessPluginId);
      setTabOptions(nextOptions);

      const _activeTab = nextOptions[0]?.value || '';
      setActiveTab(_activeTab);
      if (!_activeTab) {
        setMetricData([]);
        setOriginMetricData([]);
        setLoading(false);
        return;
      }
      setNeedsRefreshOnExpand(true);
      getInitData(_activeTab, {
        processObjectId: nextProcessObjectId,
        processPluginId: nextProcessPluginId
      });
    };

    void bootstrap();
    return () => {
      active = false;
    };
  }, [isLoading, form, plugins, monitorName]);

  useEffect(() => {
    clearTimer();
    if (frequence > 0) {
      timerRef.current = setInterval(() => {
        handleSearch('timer');
      }, frequence);
    }
    return () => clearTimer();
  }, [frequence, timeValues, metricId, activeTab]);

  useEffect(() => {
    handleSearch('refresh');
  }, [timeValues]);

  // 组件卸载时取消所有请求
  useEffect(() => {
    return () => {
      cancelAllRequests();
      clearTimer();
    };
  }, []);

  useEffect(() => {
    if (!isProcessMetricsView || !processObjectId || !hostLogicalId) {
      setProcessFilterOptions([]);
      return;
    }
    let active = true;
    setProcessFilterNames([]);
    const loadProcessOptions = async () => {
      setProcessFilterLoading(true);
      try {
        const data = await getInstanceList(processObjectId, {
          page_size: -1,
          vm_params: { instance_id: hostLogicalId },
        });
        if (!active) return;
        const options: { label: string; value: string }[] = [];
        const seen = new Set<string>();
        (data?.results || []).forEach((item: any) => {
          const name = resolveProcessNameFromInstance(item);
          if (!name || seen.has(name)) return;
          seen.add(name);
          options.push({ label: name, value: name });
        });
        options.sort((a, b) => a.label.localeCompare(b.label));
        setProcessFilterOptions(options);
      } catch {
        if (active) setProcessFilterOptions([]);
      } finally {
        if (active) setProcessFilterLoading(false);
      }
    };
    loadProcessOptions();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isProcessMetricsView, processObjectId, hostLogicalId]);

  const onTabChange = (val: string) => {
    setActiveTab(val);
    setMetricId(null);
    setProcessFilterNames([]);
    cancelAllRequests();
    setResetCounter((prev) => prev + 1);
    setNeedsRefreshOnExpand(true);
    setVisibleMetricIds(new Set());

    // 切换tab时重新初始化（需要重新获取该tab下的数据）
    getInitData(val);
  };

  // 初始化数据，包括分组和指标列表（只在弹窗时调用一次）
  const getInitData = async (
    tab: string,
    processTarget?: { processObjectId: string; processPluginId: string }
  ) => {
    const processOid = processTarget?.processObjectId || processObjectId;
    const processPid = processTarget?.processPluginId || processPluginId;
    const processTab = isHostProcessMetricsTab(tab);
    if (processTab && (!processOid || !processPid)) {
      setMetricData([]);
      setOriginMetricData([]);
      setLoading(false);
      return;
    }
    const params = {
      monitor_object_id: processTab ? processOid : monitorObject,
      monitor_plugin_id: processTab ? processPid : tab,
    };
    const getGroupList = getMetricsGroup(params);
    const getMetrics = getMonitorMetrics(params);
    setLoading(true);
    try {
      Promise.all([getGroupList, getMetrics])
        .then((res) => {
          const groupData = res[0].map((item: GroupInfo) => ({
            ...item,
            isLoading: false,
            child: [],
          }));
          const metricData = res[1];
          metricData.forEach((metric: MetricItem) => {
            const target = groupData.find(
              (item: GroupInfo) => item.id === metric.metric_group
            );
            if (target) {
              target.child.push({
                ...metric,
                viewData: [],
              });
            }
          });
          const _groupData = groupData.filter(
            (item: IndexViewItem) => !!item.child?.length
          );
          setMetricData(_groupData);
          setOriginMetricData(_groupData);
          if (_groupData.length > 0) {
            // 默认展开全部分组，避免用户逐个点开；具体指标卡仍靠滚入视图懒加载。
            setExpandedIds(new Set(_groupData.map((group: IndexViewItem) => group.id)));
          }
          setLoadedMetricIds(new Set());
          setLoadingMetricIds(new Set());
          setCancelledMetricIds(new Set());
          setVisibleMetricIds(new Set());
        })
        .finally(() => {
          setLoading(false);
        });
    } catch {
      setLoading(false);
    }
  };

  // 清空所有指标数据，但保留分组结构，并根据当前筛选状态决定显示内容
  const clearAllMetricData = () => {
    let clearedData;

    if (metricId) {
      // 如果有选中的指标，只显示该指标所在的分组
      clearedData = originMetricData
        .map((group) => ({
          ...group,
          isLoading: false,
          child: (group?.child || [])
            .filter((item) => item.id === metricId)
            .map((item) => ({
              ...item,
              viewData: [],
              seriesBudget: undefined,
            })),
        }))
        .filter((item) => item.child?.find((tex) => tex.id === metricId));
    } else {
      // 如果没有选中指标，显示所有分组和指标
      clearedData = originMetricData.map((group) => ({
        ...group,
        child: (group.child || []).map((item) => ({
          ...item,
          viewData: [],
          seriesBudget: undefined,
        })),
      }));
    }

    setMetricData(clearedData);
    setExpandedIds((prev) => {
      if (prev.size > 0) {
        const kept = new Set<number>(
          clearedData
            .map((group) => group.id)
            .filter((id): id is number => typeof id === 'number' && prev.has(id))
        );
        if (kept.size > 0) {
          return kept;
        }
      }
      return new Set<number>(
        clearedData
          .map((group) => group.id)
          .filter((id): id is number => typeof id === 'number')
      );
    });
    setLoadedMetricIds(new Set());
    setLoadingMetricIds(new Set());
    setCancelledMetricIds(new Set());
    setVisibleMetricIds(new Set());
  };

  const getParams = (item: MetricItem, ids: string[]) => {
    const labelKeys = isHostProcessMetricsTab(activeTab)
      ? ['instance_id']
      : item.instance_id_keys || [];
    const labelPairs = isHostProcessMetricsTab(activeTab)
      ? buildHostProcessLabelPairs(hostLogicalId || ids[0] || '', processFilterNames)
      : [{ keys: labelKeys, values: ids }];
    const params: SearchParams = {
      // 卡片统一用完整 query + 通用序列预算；不再走 per-metric view_query。
      query: (item.query || '').replace(
        /__\$labels__/g,
        mergeViewQueryKeyValues(labelPairs)
      ),
      source_unit: item.unit || '',
    };
    params.query_budget = 'card';
    const queryWindow = activeQueryWindowRef.current;
    if (queryWindow) {
      params.start = queryWindow.startMs;
      params.end = queryWindow.endMs;
      params.step = calculateQueryStep(
        params.start,
        params.end,
        (form as { interval?: unknown })?.interval
      );
    }
    return buildGapDetectionParams(params, (form as { interval?: unknown })?.interval);
  };

  const fetchSingleMetricData = async (
    metric: MetricItem,
    options?: { force?: boolean }
  ) => {
    if (
      !options?.force &&
      loadedMetricIds.has(metric.id) &&
      !cancelledMetricIds.has(metric.id)
    ) {
      return;
    }
    if (!options?.force && loadingMetricIds.has(metric.id)) {
      return;
    }
    const isCancelledRequest = cancelledMetricIds.has(metric.id);
    if (isCancelledRequest) {
      setCancelledMetricIds((prev) => {
        const newSet = new Set(prev);
        newSet.delete(metric.id);
        return newSet;
      });
    }
    const generation = requestGenerationRef.current;
    setLoadingMetricIds((prev) => new Set(prev).add(metric.id));
    while (activeRequestsRef.current.size >= MAX_CONCURRENT_REQUESTS) {
      await new Promise((resolve) => window.setTimeout(resolve, 30));
      if (generation !== requestGenerationRef.current) return;
    }
    if (generation !== requestGenerationRef.current) return;
    const previousController = activeRequestsRef.current.get(metric.id);
    if (previousController) {
      previousController.abort();
      activeRequestsRef.current.delete(metric.id);
    }
    const abortController = new AbortController();
    activeRequestsRef.current.set(metric.id, abortController);
    let response;
    try {
      const params = getParams(metric, form?.instance_id_values || []);
      response = await get(`/monitor/api/metrics_instance/query_range/`, {
        params,
        signal: abortController.signal,
      });
    } catch (error: any) {
      if (error.name === 'AbortError') {
        return;
      }
      return;
    }
    // 响应返回后若已被新请求替换，丢弃结果，避免 force 刷新被旧数据覆盖。
    if (activeRequestsRef.current.get(metric.id) !== abortController) {
      return;
    }
    try {
      const instanceRow = [
        {
          instance_id_values: form.instance_id_values,
          instance_name: form.instance_name,
          instance_id_keys: isHostProcessMetricsTab(activeTab)
            ? ['instance_id']
            : metric?.instance_id_keys || [],
          dimensions: metric?.dimensions || [],
          title: metric?.display_name || '--',
        },
      ];
      const chartData = response?.data?.result || [];
      const displayUnit = response?.data?.unit || '';
      const seriesBudget = response?.data?.series_budget;
      const viewData = attachGapIntervals(
        renderChart(chartData, instanceRow),
        response?.data?.gaps || []
      );
      setMetricData((prevData) => {
        const updatedData = prevData.map((group) => ({
          ...group,
          child: (group.child || []).map((item) =>
            item.id === metric.id
              ? {
                ...item,
                displayUnit,
                viewData,
                seriesBudget,
              }
              : item
          ),
        }));
        return updatedData;
      });
      // 同时更新originMetricData，保持数据同步
      setOriginMetricData((prevData) => {
        const updatedData = prevData.map((group) => ({
          ...group,
          child: (group.child || []).map((item) =>
            item.id === metric.id
              ? {
                ...item,
                displayUnit,
                viewData,
                seriesBudget,
              }
              : item
          ),
        }));
        return updatedData;
      });
      setLoadedMetricIds((prev) => {
        const newSet = new Set(prev).add(metric.id);
        return newSet;
      });
      setCancelledMetricIds((prev) => {
        if (prev.has(metric.id)) {
          const newSet = new Set(prev);
          newSet.delete(metric.id);
          return newSet;
        }
        return prev;
      });
      if (needsRefreshOnExpand) {
        setNeedsRefreshOnExpand(false);
      }
    } catch (error: any) {
      if (error.name === 'CancelledError') {
        setCancelledMetricIds((prev) => {
          const newSet = new Set(prev);
          newSet.add(metric.id);
          return newSet;
        });
        return;
      }
      return;
    } finally {
      // 仅当前请求仍占用该指标槽时清理 loading/loaded，避免 force 刷新时被中止的旧请求清掉新请求状态。
      if (activeRequestsRef.current.get(metric.id) !== abortController) {
        return;
      }
      activeRequestsRef.current.delete(metric.id);
      setLoadingMetricIds((prev) => {
        const newSet = new Set(prev);
        newSet.delete(metric.id);
        return newSet;
      });
      if (abortController.signal.aborted) {
        setLoadedMetricIds((prev) => {
          const newSet = new Set(prev);
          newSet.delete(metric.id);
          return newSet;
        });
      }
    }
  };

  const onTimeChange = (val: number[], originValue: number | null) => {
    setTimeValues({
      timeRange: val,
      originValue,
    });
  };

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const onFrequenceChange = (val: number) => {
    setFrequence(val);
  };

  const onRefresh = () => {
    setNeedsRefreshOnExpand(true);
    handleSearch('refresh');
  };

  const handleSearch = (type: string) => {
    if (type === 'refresh') {
      snapshotActiveQueryWindow();
      cancelAllRequests();
      setResetCounter((prev) => prev + 1);
      setNeedsRefreshOnExpand(true);
      clearAllMetricData();
      return;
    }
    if (type === 'timer') {
      snapshotActiveQueryWindow();
      const visibleIds = Array.from(visibleMetricIdsRef.current);
      if (!visibleIds.length) {
        return;
      }
      const visibleIdSet = new Set(visibleIds);
      metricDataRef.current.forEach((group) => {
        (group.child || []).forEach((metric: MetricItem) => {
          if (visibleIdSet.has(metric.id)) {
            void fetchSingleMetricData(metric, { force: true });
          }
        });
      });
    }
  };

  const handleMetricIdChange = (val: number) => {
    setMetricId(val);

    cancelAllRequests();
    setLoadedMetricIds(new Set());
    setLoadingMetricIds(new Set());
    setVisibleMetricIds(new Set());
    setResetCounter((prev) => prev + 1);
    setNeedsRefreshOnExpand(true);

    if (val) {
      const filteredData = originMetricData
        .map((group) => ({
          ...group,
          isLoading: false,
          child: (group?.child || [])
            .filter((item) => item.id === val)
            .map((item) => ({
              ...item,
              viewData: [],
            })),
        }))
        .filter((item) => item.child?.find((tex) => tex.id === val));

      setMetricData(filteredData);
      if (filteredData.length > 0) {
        setExpandedIds(new Set(filteredData.map((group) => group.id)));
      }
    } else {
      // 切换回全部时，清空所有指标的viewData，但保留分组结构
      const clearedData = originMetricData.map((group) => ({
        ...group,
        child: (group.child || []).map((item) => ({
          ...item,
          viewData: [], // 清空所有指标数据，让它们重新请求
        })),
      }));

      setMetricData(clearedData);
      setOriginMetricData(clearedData); // 同步更新originMetricData
      setExpandedIds(
        new Set(clearedData.map((group: IndexViewItem) => group.id))
      );
    }
  };

  const handleProcessFilterChange = (names: string[]) => {
    setProcessFilterNames(names);
    cancelAllRequests();
    setLoadedMetricIds(new Set());
    setLoadingMetricIds(new Set());
    setVisibleMetricIds(new Set());
    setResetCounter((prev) => prev + 1);
    setNeedsRefreshOnExpand(true);
    clearAllMetricData();
  };

  const handleMetricVisible = useCallback(
    (metric: MetricItem) => {
      fetchSingleMetricData(metric);
    },
    [
      loadedMetricIds,
      loadingMetricIds,
      cancelledMetricIds,
      fetchSingleMetricData,
    ]
  );

  // 处理指标可视性变化
  const handleVisibilityChange = useCallback(
    (metricId: number, isVisible: boolean) => {
      setVisibleMetricIds((prev) => {
        const newSet = new Set(prev);
        if (isVisible) {
          newSet.add(metricId);
        } else {
          newSet.delete(metricId);
        }
        return newSet;
      });
    },
    []
  );

  const toggleGroup = (expanded: boolean, groupId: number) => {
    if (expanded) {
      setExpandedIds((prev) => new Set(prev).add(groupId));

      if (needsRefreshOnExpand) {
        const groupMetrics =
          metricData.find((group) => group.id === groupId)?.child || [];
        setLoadedMetricIds((prev) => {
          const newSet = new Set(prev);
          groupMetrics.forEach((metric) => newSet.delete(metric.id));
          return newSet;
        });

        setMetricData((prevData) =>
          prevData.map((group) =>
            group.id === groupId
              ? {
                ...group,
                child: (group.child || []).map((item) => ({
                  ...item,
                  viewData: [],
                })),
              }
              : group
          )
        );
      }
    } else {
      setExpandedIds((prev) => {
        const newSet = new Set(prev);
        newSet.delete(groupId);
        return newSet;
      });
    }
  };

  const onXRangeChange = (arr: [Dayjs, Dayjs]) => {
    // 取消所有正在进行的请求
    cancelAllRequests();
    setResetCounter((prev) => prev + 1);
    setNeedsRefreshOnExpand(true);

    // 清空所有指标数据，但保留分组结构和当前筛选状态
    clearAllMetricData();

    setTimeDefaultValue((pre) => ({
      ...pre,
      rangePickerVaule: arr,
      selectValue: 0,
    }));
    const _times = arr.map((item) => dayjs(item).valueOf());
    setTimeValues({
      timeRange: _times,
      originValue: 0,
    });
  };

  const linkToSearch = (row: TableDataItem) => {
    const processTab = isHostProcessMetricsTab(activeTab);
    const _row = {
      monitor_object: String(
        processTab ? processObjectId || monitorObject : monitorObject
      ),
      plugin_id: processTab ? processPluginId || activeTab : activeTab,
      instance_id: form?.instance_id || '',
      metric_id: row.id ? String(row.id) : row.name,
    };
    const queryString = new URLSearchParams(_row).toString();
    const url = `/monitor/search?${queryString}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const linkToPolicy = (row: TableDataItem) => {
    const _row = {
      monitorName: monitorName,
      monitorObjId: monitorObject + '',
      instanceId: form?.instance_id || '',
      metricId: row.name,
      type: 'add',
    };
    const queryString = new URLSearchParams(_row).toString();
    const url = `/monitor/event/strategy/detail?${queryString}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  return (
    <div>
      <div className="flex justify-between mb-[15px] gap-3">
        <div className="flex flex-wrap gap-2 min-w-0">
          <Select
            className="w-[250px]"
            placeholder={t('common.searchPlaceHolder')}
            value={metricId}
            allowClear
            {...metricSelect.selectSearchProps}
            options={metricSelect.options}
            onChange={handleMetricIdChange}
          />
          {isProcessMetricsView ? (
            <Select
              className="min-w-[220px] max-w-[360px]"
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              maxTagCount="responsive"
              loading={processFilterLoading}
              placeholder={t('monitor.views.filterProcessPlaceholder')}
              value={processFilterNames}
              options={processFilterOptions}
              onChange={handleProcessFilterChange}
              aria-label={t('monitor.views.filterProcess')}
            />
          ) : null}
        </div>
        <TimeSelector
          defaultValue={timeDefaultValue}
          onChange={onTimeChange}
          onFrequenceChange={onFrequenceChange}
          onRefresh={onRefresh}
        />
      </div>
      <Segmented
        className="mb-[20px]"
        value={activeTab}
        options={tabOptions}
        onChange={onTabChange}
      />
      <div className="groupList">
        <Spin spinning={loading}>
          {metricData.map((metricItem) => (
            <Spin className="w-full" key={metricItem.id} spinning={false}>
              <Collapse
                className="mb-[10px]"
                title={metricItem.display_name || ''}
                isOpen={expandedIds.has(metricItem.id)}
                onToggle={(expanded) => toggleGroup(expanded, metricItem.id)}
              >
                <div className="flex flex-wrap justify-between">
                  {(metricItem.child || []).map((item) => (
                    <LazyMetricItem
                      key={`${item.id}-${resetCounter}`}
                      item={item}
                      isLoading={loadingMetricIds.has(item.id)}
                      onVisible={handleMetricVisible}
                      onSearchClick={linkToSearch}
                      onPolicyClick={linkToPolicy}
                      onXRangeChange={onXRangeChange}
                      resetKey={resetCounter}
                      isLoaded={loadedMetricIds.has(item.id)}
                      isCancelled={cancelledMetricIds.has(item.id)}
                      onVisibilityChange={handleVisibilityChange}
                      isInViewport={visibleMetricIds.has(item.id)}
                      xAxisDomain={activeQueryWindow?.xAxisDomain}
                    />
                  ))}
                </div>
              </Collapse>
            </Spin>
          ))}
        </Spin>
      </div>
    </div>
  );
};

export default MonitorView;
