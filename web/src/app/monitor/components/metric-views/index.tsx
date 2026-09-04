'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Pagination, Spin, Select, Segmented } from 'antd';
import TimeSelector from '@/components/time-selector';
import Collapse from '@/components/collapse';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import {
  TableDataItem,
  TimeSelectorDefaultValue,
  TimeValuesProps,
  IntegrationItem,
  MetricItem,
  IndexViewItem
} from '@/app/monitor/types';
import { ViewDetailProps } from '@/app/monitor/types/view';
import { SearchParams } from '@/app/monitor/types/search';
import { useTranslation } from '@/utils/i18n';
import {
  mergeViewQueryKeyValues,
  renderChart,
  getRecentTimeRange
} from '@/app/monitor/utils/common';
import { loadMonitorPluginsByObjectCached } from '@/app/monitor/utils/monitorPluginCache';
import { calculateQueryStep } from '@/app/monitor/utils/queryStep';
import { attachGapIntervals, buildGapDetectionParams } from '@/app/monitor/utils/gapIntervals';

import dayjs, { Dayjs } from 'dayjs';
import LazyMetricItem from './lazyMetricItem';
import {
  filterMetricGroupsByIds,
  useMetricSelectOptions,
} from '@/app/monitor/components/metricSelectOptions';
import { buildSearchTimeQueryParams } from '@/app/monitor/utils/searchTimeQuery';
import {
  buildHostProcessLabelPairs,
  isHostMonitorObject,
  isHostProcessMetricsTab,
  resolveHostProcessMetricsTarget,
  resolveProcessNameFromInstance,
  withHostProcessMetricsTab
} from '@/app/monitor/dashboards/objects/host/host-process-metrics-tab';

const MYSQL_GROUP_NAME_MAP: Record<string, string> = {
  ConnStatus: '连接状态',
  KeyCache: '键缓存',
  TempTable: '临时表',
  InnoDBPerf: 'InnoDB 性能',
  Replication: '复制状态'
};

const MYSQL_METRIC_NAME_MAP: Record<string, string> = {
  mysql_process_list_threads_idle: '空闲线程数',
  mysql_process_list_threads_executing: '执行线程数',
  mysql_process_list_threads_sending_data: '发送数据线程数',
  mysql_process_list_threads_waiting_for_lock: '锁等待线程数',
  mysql_queries_rate: '查询吞吐速率',
  mysql_questions_rate: '请求语句速率',
  mysql_com_select_rate: '查询语句速率',
  mysql_com_insert_rate: '插入语句速率',
  mysql_com_update_rate: '更新语句速率',
  mysql_com_delete_rate: '删除语句速率',
  mysql_innodb_os_log_fsyncs_rate: 'Redo 刷盘',
  mysql_innodb_buffer_pool_read_requests_rate: '缓冲池读请求速率',
  mysql_innodb_buffer_pool_reads_rate: '缓冲池磁盘读取速率',
  mysql_buffer_pool_hit_ratio: '缓冲池命中率',
  mysql_buffer_pool_used_ratio: '缓冲池使用率',
  mysql_innodb_buffer_pool_pages_total: '缓冲池总页数',
  mysql_innodb_buffer_pool_pages_dirty: '缓冲池脏页数',
  mysql_innodb_buffer_pool_pages_free: '缓冲池空闲页数',
  mysql_key_reads_rate: '键缓存磁盘读取速率',
  mysql_key_read_requests_rate: '键缓存读取请求速率',
  mysql_key_cache_hit_ratio: '键缓存命中率',
  mysql_variables_innodb_buffer_pool_size: '缓冲池配置大小',
  mysql_variables_read_only: '只读状态',
  mysql_variables_super_read_only: '超级只读状态',
  mysql_variables_log_bin: '二进制日志状态',
  mysql_variables_log_slave_updates: '复制回放写入日志状态',
  mysql_innodb_data_fsyncs_rate: 'InnoDB 数据文件刷盘速率'
};

const normalizeMysqlDisplayName = (name = '') => name
  .replace(/QPS\s*\(Queries\)/gi, '查询吞吐速率')
  .replace(/Questions/gi, '请求语句')
  .replace(/Sending data/gi, '发送数据')
  .replace(/Locked/gi, '锁等待')
  .replace(/Sleep/gi, '空闲')
  .replace(/Query/gi, '执行')
  .replace(/SELECT/gi, '查询语句')
  .replace(/INSERT/gi, '插入语句')
  .replace(/UPDATE/gi, '更新语句')
  .replace(/DELETE/gi, '删除语句')
  .replace(/Buffer Pool/gi, '缓冲池')
  .replace(/Key Cache/gi, '键缓存')
  .replace(/Redo\s+Fsync/gi, 'Redo 刷盘')
  .replace(/Fsync/gi, '刷盘')
  .replace(/Read Only/gi, '只读状态')
  .replace(/Super Read Only/gi, '超级只读状态')
  .replace(/Log Bin/gi, '二进制日志状态')
  .replace(/Log Slave Updates/gi, '复制回放写入日志状态')
  .replace(/\s+/g, ' ')
  .trim();

const MetricViews: React.FC<ViewDetailProps> = ({
  monitorObjectId,
  monitorObjectName,
  instanceId,
  instanceName,
  idValues,
  queryInstanceIdKeys,
  externalTimeValues,
  externalTimeDefaultValue,
  externalFrequence,
  externalRefreshSignal,
  collectionInterval,
  hideTimeSelector = false,
  onExternalXRangeChange
}) => {
  const { isLoading } = useApiClient();
  const {
    getEffectivePlugins,
    getMonitorObject,
    getMonitorPlugin,
    getMonitorMetrics,
    getMetricsGroup,
    getInstanceList
  } = useMonitorApi();
  const { get } = useApiClient();
  const { t } = useTranslation();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const metricSearchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [metricIds, setMetricIds] = useState<number[]>([]);
  const [timeValues, setTimeValues] = useState<TimeValuesProps>({
    timeRange: [],
    originValue: 15
  });
  const [timeDefaultValue, setTimeDefaultValue] =
    useState<TimeSelectorDefaultValue>({
      selectValue: 15,
      rangePickerVaule: null
    });
  const [frequence, setFrequence] = useState<number>(0);
  const [metricData, setMetricData] = useState<IndexViewItem[]>([]);
  const [originMetricData, setOriginMetricData] = useState<IndexViewItem[]>([]);
  const [metricPage, setMetricPage] = useState(1);
  const [metricCount, setMetricCount] = useState(0);
  const [metricKeyword, setMetricKeyword] = useState('');
  const [activeTab, setActiveTab] = useState<string>('');
  const [plugins, setPlugins] = useState<{ label: string; value: string }[]>([]);
  const [processObjectId, setProcessObjectId] = useState('');
  const [processPluginId, setProcessPluginId] = useState('');
  const [processFilterNames, setProcessFilterNames] = useState<string[]>([]);
  const [processFilterOptions, setProcessFilterOptions] = useState<
    { label: string; value: string }[]
  >([]);
  const [processFilterLoading, setProcessFilterLoading] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const metricSelect = useMetricSelectOptions(originMetricData);

  // 添加懒加载和请求管理相关状态
  const [loadedMetricIds, setLoadedMetricIds] = useState<Set<number>>(
    new Set()
  );
  const [loadingMetricIds, setLoadingMetricIds] = useState<Set<number>>(
    new Set()
  );
  const [cancelledMetricIds, setCancelledMetricIds] = useState<Set<number>>(
    new Set()
  );
  const [visibleMetricIds, setVisibleMetricIds] = useState<Set<number>>(
    new Set()
  );
  const [resetCounter, setResetCounter] = useState<number>(0);
  const [needsRefreshOnExpand, setNeedsRefreshOnExpand] =
    useState<boolean>(false);
  const lastExternalRefreshSignalRef = useRef<number | undefined>(externalRefreshSignal);

  // 大量指标卡片同时请求会挤占浏览器、VictoriaMetrics 和 Telegraf 的资源。
  // 只允许可视区域及下一行卡片以最多四路请求排队加载。
  const MAX_CONCURRENT_REQUESTS = 4;
  const activeRequestsRef = useRef<Map<number, AbortController>>(new Map());
  const metricCatalogAbortRef = useRef<AbortController | null>(null);
  const requestGenerationRef = useRef(0);
  const visibleMetricIdsRef = useRef<Set<number>>(new Set());
  const metricDataRef = useRef<IndexViewItem[]>([]);
  const isMysqlView = String(monitorObjectName || '').toLowerCase() === 'mysql';
  const isHostView = isHostMonitorObject(monitorObjectName);
  const isProcessMetricsView = isHostProcessMetricsTab(activeTab);
  const activeTimeValues = externalTimeValues || timeValues;
  const activeTimeDefaultValue = externalTimeDefaultValue || timeDefaultValue;
  const activeFrequence = typeof externalFrequence === 'number' ? externalFrequence : frequence;

  visibleMetricIdsRef.current = visibleMetricIds;
  metricDataRef.current = metricData;

  const resolveQueryInstanceIdKeys = (metricKeys?: string[]) => {
    if (isProcessMetricsView) return ['instance_id'];
    if (queryInstanceIdKeys?.length) return queryInstanceIdKeys;
    return metricKeys || [];
  };

  const hostLogicalId = String(idValues?.[0] || '').trim();

  const getDisplayName = (item: { name?: string; display_name?: string }) => {
    const displayName = item.display_name || item.name || '--';
    if (!isMysqlView) {
      return displayName;
    }
    return MYSQL_METRIC_NAME_MAP[item.name || ''] || MYSQL_GROUP_NAME_MAP[displayName] || normalizeMysqlDisplayName(displayName);
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
          vm_params: { instance_id: hostLogicalId }
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
    // getInstanceList 来自 hook，身份不稳定；仅随主机/进程对象/页签变化重载。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isProcessMetricsView, processObjectId, hostLogicalId]);

  useEffect(() => {
    if (isLoading) {
      return;
    }
    initPage();
  }, [isLoading, monitorObjectId, instanceId]);

  useEffect(() => {
    clearTimer();
    if (activeFrequence > 0) {
      timerRef.current = setInterval(() => {
        handleSearch('timer');
      }, activeFrequence);
    }
    return () => clearTimer();
  }, [activeFrequence, activeTimeValues, metricIds.join(','), activeTab]);

  useEffect(() => {
    handleSearch('refresh');
  }, [activeTimeValues]);

  // 组件卸载时取消所有请求
  useEffect(() => {
    return () => {
      cancelAllRequests();
      metricCatalogAbortRef.current?.abort();
      clearTimer();
      if (metricSearchTimerRef.current) {
        clearTimeout(metricSearchTimerRef.current);
      }
    };
  }, []);

  const initPage = async () => {
    if (!monitorObjectId || !instanceId) {
      setPlugins([]);
      setActiveTab('');
      setMetricData([]);
      setOriginMetricData([]);
      setProcessObjectId('');
      setProcessPluginId('');
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      let responseData: IntegrationItem[] = [];

      // 外部已指定 queryInstanceIdKeys 时（纯进程对象视图）直接拉插件列表。
      if (queryInstanceIdKeys?.length && !isHostView) {
        try {
          const list = await loadMonitorPluginsByObjectCached(
            monitorObjectId,
            () =>
              getMonitorPlugin({
                monitor_object_id: monitorObjectId
              })
          );
          responseData = list as IntegrationItem[];
        } catch {
          responseData = [];
        }
      } else {
        try {
          const effective = await getEffectivePlugins(monitorObjectId, {
            instance_id: instanceId
          });
          responseData = Array.isArray(effective) ? effective : [];
        } catch {
          responseData = [];
        }
      }

      let _plugins: { label: string; value: string }[] = responseData
        .sort((a: IntegrationItem, b: IntegrationItem) => {
          const order = (item: IntegrationItem) =>
            item.is_pre ? 0 : !item.is_custom ? 1 : 2;
          return order(a) - order(b);
        })
        .map((item: IntegrationItem) => ({
          label: String(item.display_name || item.name || '--'),
          value: String(item.id)
        }));

      let nextProcessObjectId = '';
      let nextProcessPluginId = '';
      if (isHostView) {
        const target = await resolveHostProcessMetricsTarget({
          getMonitorObject,
          getMonitorPlugin
        });
        if (target) {
          nextProcessObjectId = target.processObjectId;
          nextProcessPluginId = target.processPluginId;
          _plugins = withHostProcessMetricsTab(
            _plugins,
            true,
            target.processPluginLabel
          );
        }
      }
      setProcessObjectId(nextProcessObjectId);
      setProcessPluginId(nextProcessPluginId);

      setPlugins(_plugins);
      const _activeTab = _plugins[0]?.value || '';
      setActiveTab(_activeTab);
      if (!_activeTab) {
        setMetricData([]);
        setOriginMetricData([]);
        return;
      }
      await getInitData(_activeTab, {
        processObjectId: nextProcessObjectId,
        processPluginId: nextProcessPluginId
      });
    } catch {
      setPlugins([]);
      setActiveTab('');
      setMetricData([]);
      setOriginMetricData([]);
      setProcessObjectId('');
      setProcessPluginId('');
    } finally {
      setLoading(false);
    }
  };

  const onTabChange = (val: string) => {
    if (metricSearchTimerRef.current) {
      clearTimeout(metricSearchTimerRef.current);
    }
    setActiveTab(val);
    setMetricIds([]);
    setMetricPage(1);
    setMetricKeyword('');
    setProcessFilterNames([]);
    cancelAllRequests();
    setResetCounter((prev) => prev + 1);
    setNeedsRefreshOnExpand(true);
    setVisibleMetricIds(new Set());
    getInitData(val, undefined, 1, '');
  };

  const getInitData = async (
    tab: string,
    processTarget?: { processObjectId: string; processPluginId: string },
    page = 1,
    keyword = ''
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
      monitor_object_id: processTab ? processOid : String(monitorObjectId),
      monitor_plugin_id: processTab ? processPid : tab,
      page,
      ...(keyword.trim() ? { keyword: keyword.trim() } : {})
    };
    metricCatalogAbortRef.current?.abort();
    const abortController = new AbortController();
    metricCatalogAbortRef.current = abortController;
    const config = { signal: abortController.signal };
    setLoading(true);
    try {
      const res = await Promise.all([
        getMetricsGroup(params, config),
        getMonitorMetrics(params, config)
      ]);
      if (abortController.signal.aborted) return;
      const groupData: IndexViewItem[] = (
        res[1].metric_groups || res[0].items
      ).map((item) => ({
        ...item,
        id: Number(item.id),
        display_name: getDisplayName(item),
        isLoading: false,
        child: []
      }));
      const metricsList = res[1].items;
      setMetricCount(res[1].count);
      metricsList.forEach((metric: MetricItem) => {
        const target = groupData.find(
          (item) => item.id === metric.metric_group
        );
        if (target) {
          target.child.push({
            ...metric,
            display_name: getDisplayName(metric),
            viewData: []
          });
        }
      });
      const _groupData = groupData.filter((item) => !!item.child?.length);
      setMetricData(_groupData);
      setOriginMetricData(_groupData);
      if (_groupData.length > 0) {
        // 默认展开全部分组，避免用户逐个点开；具体指标卡仍靠滚入视图懒加载。
        setExpandedIds(new Set(_groupData.map((group) => group.id)));
      }
      setLoadedMetricIds(new Set());
      setLoadingMetricIds(new Set());
      setCancelledMetricIds(new Set());
      setVisibleMetricIds(new Set());
    } catch {
      if (!abortController.signal.aborted) {
        setMetricData([]);
        setOriginMetricData([]);
      }
    } finally {
      if (metricCatalogAbortRef.current === abortController) {
        setLoading(false);
      }
    }
  };

  // 清空所有指标数据，但保留分组结构，并根据当前筛选状态决定显示内容
  const clearAllMetricData = () => {
    const clearedData = filterMetricGroupsByIds(originMetricData, metricIds);

    setMetricData(clearedData);
    // 刷新时保留已展开分组；若为空则展开全部，继续靠卡片滚入视图加载。
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
    const labelKeys = resolveQueryInstanceIdKeys(item.instance_id_keys || []);
    const labelPairs = isProcessMetricsView
      ? buildHostProcessLabelPairs(hostLogicalId || ids[0] || '', processFilterNames)
      : [{ keys: labelKeys, values: ids }];
    const params: SearchParams = {
      // 卡片统一用完整 query + 通用序列预算；不再走 per-metric view_query。
      query: (item.query || '').replace(
        /__\$labels__/g,
        mergeViewQueryKeyValues(labelPairs)
      ),
      source_unit: item.unit || ''
    };
    // 完整明细仍由搜索页查询（不带 query_budget）。
    params.query_budget = 'card';
    const recentTimeRange = getRecentTimeRange(activeTimeValues);
    const startTime = recentTimeRange.at(0);
    const endTime = recentTimeRange.at(1);
    if (Number.isFinite(startTime) && Number.isFinite(endTime)) {
      params.start = startTime;
      params.end = endTime;
      params.step = calculateQueryStep(params.start, params.end, collectionInterval);
    }
    return buildGapDetectionParams(params, collectionInterval);
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
    // 不再取消最早请求。超出并发上限的可视卡片在这里排队，直到有空槽。
    while (activeRequestsRef.current.size >= MAX_CONCURRENT_REQUESTS) {
      await new Promise((resolve) => window.setTimeout(resolve, 30));
      if (generation !== requestGenerationRef.current) return;
    }
    if (generation !== requestGenerationRef.current) return;
    // force 刷新时中止同指标旧请求，避免竞态覆盖。
    const previousController = activeRequestsRef.current.get(metric.id);
    if (previousController) {
      previousController.abort();
      activeRequestsRef.current.delete(metric.id);
    }
    const abortController = new AbortController();
    activeRequestsRef.current.set(metric.id, abortController);
    let response;
    try {
      const params = getParams(metric, idValues);
      response = await get(`/monitor/api/metrics_instance/query_range/`, {
        params,
        signal: abortController.signal
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
          instance_id_values: idValues,
          instance_name: instanceName,
          instance_id_keys: resolveQueryInstanceIdKeys(
            metric?.instance_id_keys || []
          ),
          dimensions: metric?.dimensions || [],
          title: metric?.display_name || '--'
        }
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
                seriesBudget
              }
              : item
          )
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
                seriesBudget
              }
              : item
          )
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
      originValue
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
      cancelAllRequests();
      setResetCounter((prev) => prev + 1);
      setNeedsRefreshOnExpand(true);
      clearAllMetricData();
      return;
    }
    if (type === 'timer') {
      // 定时刷新只重拉当前视口内卡片，保留离屏 viewData，避免全量清空导致卡顿。
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

  useEffect(() => {
    if (externalRefreshSignal === undefined) {
      return;
    }

    if (lastExternalRefreshSignalRef.current === externalRefreshSignal) {
      return;
    }

    lastExternalRefreshSignalRef.current = externalRefreshSignal;
    handleSearch('refresh');
  }, [externalRefreshSignal]);

  const handleMetricVisible = useCallback(
    (metric: MetricItem) => {
      fetchSingleMetricData(metric);
    },
    [
      loadedMetricIds,
      loadingMetricIds,
      cancelledMetricIds,
      fetchSingleMetricData
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

  const handleMetricIdChange = (val: number[]) => {
    const nextIds = val || [];
    setMetricIds(nextIds);

    cancelAllRequests();
    setLoadedMetricIds(new Set());
    setLoadingMetricIds(new Set());
    setVisibleMetricIds(new Set());
    setResetCounter((prev) => prev + 1);
    setNeedsRefreshOnExpand(true);

    const filteredData = filterMetricGroupsByIds(originMetricData, nextIds);
    setMetricData(filteredData);
    if (!nextIds.length) {
      // 切换回全部时，同步清空 origin，让后续刷新重新请求
      setOriginMetricData(filteredData);
    }
    setExpandedIds(
      new Set(
        filteredData
          .map((group: IndexViewItem) => group.id)
          .filter((id): id is number => typeof id === 'number')
      )
    );
  };

  const handleMetricKeywordChange = (value: string) => {
    setMetricKeyword(value);
    if (metricSearchTimerRef.current) {
      clearTimeout(metricSearchTimerRef.current);
    }
    metricSearchTimerRef.current = setTimeout(() => {
      setMetricPage(1);
      setMetricIds([]);
      cancelAllRequests();
      getInitData(activeTab, undefined, 1, value);
    }, 300);
  };

  const handleMetricPageChange = (page: number) => {
    setMetricPage(page);
    setMetricIds([]);
    cancelAllRequests();
    setResetCounter((prev) => prev + 1);
    getInitData(activeTab, undefined, page, metricKeyword);
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
                  viewData: []
                }))
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

    if (externalTimeValues && onExternalXRangeChange) {
      onExternalXRangeChange(arr);
      return;
    }

    setTimeDefaultValue((pre) => ({
      ...pre,
      rangePickerVaule: arr,
      selectValue: 0
    }));
    const _times = arr.map((item) => dayjs(item).valueOf());
    setTimeValues({
      timeRange: _times,
      originValue: 0
    });
  };

  const linkToSearch = (row: TableDataItem) => {
    const processTab = isHostProcessMetricsTab(activeTab);
    const _row = {
      monitor_object: String(
        processTab ? processObjectId || monitorObjectId : monitorObjectId
      ),
      plugin_id: processTab ? processPluginId || activeTab : activeTab,
      instance_id: instanceId as string,
      metric_id: row.id ? String(row.id) : row.name,
      ...buildSearchTimeQueryParams(timeValues)
    };
    const queryString = new URLSearchParams(_row).toString();
    const url = `/monitor/search?${queryString}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const linkToPolicy = (row: TableDataItem) => {
    const _row = {
      monitorName: monitorObjectName,
      monitorObjId: String(monitorObjectId),
      instanceId: instanceId as string,
      metricId: row.name,
      type: 'add'
    };
    const queryString = new URLSearchParams(_row).toString();
    const url = `/monitor/event/strategy/detail?${queryString}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="w-full h-full">
      <Segmented
        className="mb-[16px]"
        value={activeTab}
        options={plugins}
        onChange={onTabChange}
      />
      <div className="flex justify-between mb-[16px] gap-3">
        <div className="flex flex-wrap gap-2 min-w-0">
          <Select
            className="min-w-[250px] max-w-[360px]"
            mode="multiple"
            maxTagCount="responsive"
            placeholder={t('common.searchPlaceHolder')}
            value={metricIds}
            allowClear
            {...metricSelect.selectSearchProps}
            options={metricSelect.options}
            onSearch={handleMetricKeywordChange}
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
        {!hideTimeSelector ? (
          <TimeSelector
            defaultValue={activeTimeDefaultValue}
            onChange={onTimeChange}
            onFrequenceChange={onFrequenceChange}
            onRefresh={onRefresh}
          />
        ) : null}
      </div>
      <div className="groupList h-[calc(100vh-240px)] overflow-y-auto">
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
                    />
                  ))}
                </div>
              </Collapse>
            </Spin>
          ))}
        </Spin>
      </div>
      {metricCount > 100 && (
        <div className="mt-4 flex justify-end">
          <Pagination
            current={metricPage}
            pageSize={100}
            showSizeChanger={false}
            total={metricCount}
            onChange={handleMetricPageChange}
          />
        </div>
      )}
    </div>
  );
};
export default MetricViews;
