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
  getRecentTimeRange,
} from '@/app/monitor/utils/common';
import dayjs, { Dayjs } from 'dayjs';
import { INIT_VIEW_MODAL_FORM } from '@/app/monitor/constants/view';
import LazyMetricItem from './lazyMetricItem';

const MonitorView: React.FC<ViewModalProps> = ({
  monitorObject,
  monitorName,
  plugins,
  form = INIT_VIEW_MODAL_FORM,
}) => {
  const { isLoading } = useApiClient();
  const { get } = useApiClient();
  const { getMetricsGroup, getMonitorMetrics } = useMonitorApi();
  const { t } = useTranslation();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [metricId, setMetricId] = useState<number | null>();
  const [timeValues, setTimeValues] = useState<TimeValuesProps>({
    timeRange: [],
    originValue: 15,
  });
  const [timeDefaultValue, setTimeDefaultValue] =
    useState<TimeSelectorDefaultValue>({
      selectValue: 15,
      rangePickerVaule: null,
    });
  const [frequence, setFrequence] = useState<number>(0);
  const [metricData, setMetricData] = useState<IndexViewItem[]>([]);
  const [originMetricData, setOriginMetricData] = useState<IndexViewItem[]>([]);
  const [activeTab, setActiveTab] = useState<string>('');
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
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

  // 请求并发控制
  const MAX_CONCURRENT_REQUESTS = 12;
  const activeRequestsRef = useRef<Map<number, AbortController>>(new Map());
  const requestQueueRef = useRef<number[]>([]);

  const cancelRequest = (metricId: number) => {
    const abortController = activeRequestsRef.current.get(metricId);
    if (abortController) {
      abortController.abort();
      activeRequestsRef.current.delete(metricId);
    }
    requestQueueRef.current = requestQueueRef.current.filter(
      (id) => id !== metricId
    );

    setCancelledMetricIds((prev) => new Set(prev).add(metricId));

    setLoadingMetricIds((prev) => {
      const newSet = new Set(prev);
      newSet.delete(metricId);
      return newSet;
    });

    setLoadedMetricIds((prev) => {
      const newSet = new Set(prev);
      newSet.delete(metricId);
      return newSet;
    });
  };

  const cancelAllRequests = () => {
    const cancelledIds = Array.from(activeRequestsRef.current.keys());

    activeRequestsRef.current.forEach((abortController) => {
      abortController.abort();
    });
    activeRequestsRef.current.clear();
    requestQueueRef.current = [];

    setCancelledMetricIds((prev) => {
      const newSet = new Set(prev);
      cancelledIds.forEach((id) => newSet.add(id));
      return newSet;
    });

    setLoadingMetricIds(new Set());
  };

  const manageRequestQueue = (newMetricId: number) => {
    if (activeRequestsRef.current.size >= MAX_CONCURRENT_REQUESTS) {
      const oldestMetricId = requestQueueRef.current.shift();
      if (oldestMetricId !== undefined) {
        cancelRequest(oldestMetricId);
        setLoadingMetricIds((prev) => {
          const newSet = new Set(prev);
          newSet.delete(oldestMetricId);
          return newSet;
        });
      }
    }

    requestQueueRef.current.push(newMetricId);
  };

  useEffect(() => {
    if (isLoading) {
      return;
    }
    if (form?.instance_id_values.length) {
      const _activeTab = plugins[0]?.value || '';
      setActiveTab(_activeTab);
      setNeedsRefreshOnExpand(true);
      getInitData(_activeTab);
    }
  }, [isLoading, form]);

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

  const onTabChange = (val: string) => {
    setActiveTab(val);
    setMetricId(null);
    cancelAllRequests();
    setResetCounter((prev) => prev + 1);
    setNeedsRefreshOnExpand(true);
    setVisibleMetricIds(new Set());

    // 切换tab时重新初始化（需要重新获取该tab下的数据）
    getInitData(val);
  };

  // 初始化数据，包括分组和指标列表（只在弹窗时调用一次）
  const getInitData = async (tab: string) => {
    const params = {
      monitor_object_id: monitorObject,
      monitor_plugin_id: tab,
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
            setExpandedIds(
              new Set(_groupData.map((group: IndexViewItem) => group.id))
            );
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
        })),
      }));
    }

    setMetricData(clearedData);
    // 更新展开状态
    if (clearedData.length > 0) {
      setExpandedIds(new Set(clearedData.map((group) => group.id)));
    }
    setLoadedMetricIds(new Set());
    setLoadingMetricIds(new Set());
    setCancelledMetricIds(new Set());
    setVisibleMetricIds(new Set());
  };

  const getParams = (item: MetricItem, ids: string[]) => {
    const params: SearchParams = {
      query: (item.query || '').replace(
        /__\$labels__/g,
        mergeViewQueryKeyValues([
          { keys: item.instance_id_keys || [], values: ids },
        ])
      ),
    };
    const recentTimeRange = getRecentTimeRange(timeValues);
    const startTime = recentTimeRange.at(0);
    const endTime = recentTimeRange.at(1);
    const MAX_POINTS = 100;
    const DEFAULT_STEP = 360;
    if (startTime && endTime) {
      params.start = startTime;
      params.end = endTime;
      params.step = Math.max(
        Math.ceil(
          (params.end / MAX_POINTS - params.start / MAX_POINTS) / DEFAULT_STEP
        ),
        1
      );
    }
    return params;
  };

  const fetchSingleMetricData = async (metric: MetricItem) => {
    if (loadedMetricIds.has(metric.id) && !cancelledMetricIds.has(metric.id)) {
      return;
    }

    if (loadingMetricIds.has(metric.id)) {
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

    const abortController = new AbortController();

    activeRequestsRef.current.set(metric.id, abortController);

    manageRequestQueue(metric.id);

    const currentController = activeRequestsRef.current.get(metric.id);
    if (!currentController || currentController.signal.aborted) {
      return;
    }

    setLoadingMetricIds((prev) => new Set(prev).add(metric.id));

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

    try {
      const instanceRow = [
        {
          instance_id_values: form.instance_id_values,
          instance_name: form.instance_name,
          instance_id_keys: metric?.instance_id_keys || [],
          dimensions: metric?.dimensions || [],
          title: metric?.display_name || '--',
        },
      ];

      let chartData = [];
      if (response && response.data && response.data.result) {
        chartData = response.data.result;
      } else if (response && response.data) {
        chartData = Array.isArray(response.data) ? response.data : [];
      } else if (Array.isArray(response)) {
        chartData = response;
      }

      const viewData = renderChart(chartData, instanceRow);

      setMetricData((prevData) => {
        const updatedData = prevData.map((group) => ({
          ...group,
          child: (group.child || []).map((item) =>
            item.id === metric.id
              ? {
                ...item,
                viewData: viewData,
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
                viewData: viewData,
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
      if (activeRequestsRef.current.get(metric.id) === abortController) {
        activeRequestsRef.current.delete(metric.id);
        requestQueueRef.current = requestQueueRef.current.filter(
          (id) => id !== metric.id
        );
      }

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
    if (['refresh', 'timer'].includes(type)) {
      cancelAllRequests();
      setResetCounter((prev) => prev + 1);
      setNeedsRefreshOnExpand(true);

      // 使用新的clearAllMetricData函数清空所有指标数据
      clearAllMetricData();
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
    const _row = {
      monitor_object: monitorObject + '',
      instance_id: form?.instance_id || '',
      metric_id: row.name,
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
      <div className="flex justify-between mb-[15px]">
        <Select
          className="w-[250px]"
          placeholder={t('common.searchPlaceHolder')}
          value={metricId}
          allowClear
          showSearch
          options={originMetricData.map((item) => ({
            label: item.display_name,
            title: item.name,
            options: (item.child || []).map((tex) => ({
              label: tex.display_name,
              value: tex.id,
            })),
          }))}
          onChange={handleMetricIdChange}
        ></Select>
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
        options={plugins}
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
