'use client';
import React, { useState, useEffect, useRef, useMemo, RefObject } from 'react';
import { Select, Spin, Empty } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import LineChart from '@/app/monitor/components/charts/lineChart';
import {
  ChartData,
  MetricItem,
  ThresholdField,
  FilterItem,
  TableDataItem,
} from '@/app/monitor/types';
import { SourceFeild } from '@/app/monitor/types/event';
import { InstanceItem } from '@/app/monitor/types/search';
import {
  mergeViewQueryKeyValues,
  renderChart,
} from '@/app/monitor/utils/common';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';

const { Option } = Select;

interface MetricPreviewProps {
  monitorObjId: string | null;
  source: SourceFeild;
  metric: string | null;
  metrics: MetricItem[];
  groupBy: string[];
  conditions: FilterItem[];
  period: number | null;
  periodUnit: string;
  algorithm: string | null;
  threshold: ThresholdField[];
  calculationUnit?: string | null;
  scrollContainerRef?: RefObject<HTMLDivElement | null>;
  anchorRef?: RefObject<HTMLDivElement | null>;
}

const MetricPreview: React.FC<MetricPreviewProps> = ({
  monitorObjId,
  source,
  metric,
  metrics,
  groupBy,
  conditions,
  period,
  periodUnit,
  algorithm,
  threshold,
  calculationUnit,
  scrollContainerRef,
  anchorRef,
}) => {
  const { t } = useTranslation();
  const { get } = useApiClient();
  const { getInstanceList } = useMonitorApi();
  const { findUnitNameById } = useUnitTransform();
  const [loading, setLoading] = useState<boolean>(false);
  const [instanceLoading, setInstanceLoading] = useState<boolean>(false);
  const [chartData, setChartData] = useState<ChartData[]>([]);
  const [unit, setUnit] = useState<string>('');
  const [selectedInstance, setSelectedInstance] = useState<string | null>(null);
  const [instances, setInstances] = useState<InstanceItem[]>([]);
  const [allInstances, setAllInstances] = useState<TableDataItem[]>([]);
  const [topOffset, setTopOffset] = useState<number>(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  const instanceAbortControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef<number>(0);
  const previewRef = useRef<HTMLDivElement>(null);

  // 逻辑：预览组件始终可见，通过调整 top 值确保不覆盖"基本信息"区域
  useEffect(() => {
    const scrollContainer = scrollContainerRef?.current;
    const anchorElement = anchorRef?.current;
    if (!scrollContainer || !anchorElement) {
      setTopOffset(0);
      return;
    }
    const handleScroll = () => {
      const containerRect = scrollContainer.getBoundingClientRect();
      const anchorRect = anchorElement.getBoundingClientRect();
      // 计算"基本信息"底部相对于滚动容器顶部的位置
      const anchorBottomRelativeToContainer =
        anchorRect.bottom - containerRect.top;
      const minTop = Math.max(0, anchorBottomRelativeToContainer + 16);
      setTopOffset(minTop);
    };
    // 初始计算
    handleScroll();
    scrollContainer.addEventListener('scroll', handleScroll);
    return () => {
      scrollContainer.removeEventListener('scroll', handleScroll);
    };
  }, [scrollContainerRef, anchorRef]);

  useEffect(() => {
    if (!monitorObjId) return;
    getInstances();
  }, [monitorObjId]);

  // 根据 source.type 和 source.values 设置资产列表
  useEffect(() => {
    if (source?.type !== 'instance' || !source?.values?.length) {
      setInstances([]);
      setSelectedInstance(null);
      return;
    }
    const instanceItems: InstanceItem[] = source.values.map((val: string) => {
      return {
        instance_id: val,
        instance_name: val,
        instance_id_values: [val],
      };
    });
    setInstances(instanceItems);
    if (instanceItems.length > 0) {
      const currentExists = instanceItems.some(
        (item) => item.instance_id === selectedInstance
      );
      if (!currentExists) {
        setSelectedInstance(instanceItems[0].instance_id);
      }
    }
  }, [source?.type, source?.values]);

  // 判断是否可以查询
  const canQuery = useMemo(() => {
    return !!(
      monitorObjId &&
      metric &&
      selectedInstance &&
      instances.length > 0
    );
  }, [monitorObjId, metric, selectedInstance, instances.length]);

  // 获取当前选中的指标信息
  const currentMetric = useMemo(() => {
    return metrics.find((item) => item.name === metric);
  }, [metrics, metric]);

  // 将汇聚周期转换为秒
  const getPeriodInSeconds = (): number => {
    const periodValue = period || 5;
    switch (periodUnit) {
      case 'min':
        return periodValue * 60;
      case 'hour':
        return periodValue * 3600;
      case 'day':
        return periodValue * 86400;
      default:
        return periodValue * 60;
    }
  };

  // 获取汇聚周期的时间字符串（用于 PromQL）
  const getPeriodString = (): string => {
    const periodValue = period || 5;
    switch (periodUnit) {
      case 'min':
        return `${periodValue}m`;
      case 'hour':
        return `${periodValue}h`;
      case 'day':
        return `${periodValue}d`;
      default:
        return `${periodValue}m`;
    }
  };

  // 根据汇聚方式包装查询语句
  const wrapQueryWithAlgorithm = (baseQuery: string): string => {
    if (!algorithm) return baseQuery;
    const periodStr = getPeriodString();
    const groupByClause = groupBy?.length ? ` by (${groupBy.join(', ')})` : '';
    // _over_time 函数需要时间范围参数
    const overTimeFunctions = [
      'sum_over_time',
      'max_over_time',
      'min_over_time',
      'avg_over_time',
      'last_over_time',
      'count_over_time',
    ];
    if (overTimeFunctions.includes(algorithm)) {
      // 例如: sum_over_time(metric{labels}[5m])
      return `${algorithm}(${baseQuery}[${periodStr}])${groupByClause}`;
    } else {
      // 聚合函数如 sum, avg, max, min, count
      // 例如: sum by (instance_id) (metric{labels})
      return `${algorithm}${groupByClause}(${baseQuery})`;
    }
  };

  // 构建查询参数
  const getQueryParams = () => {
    if (!currentMetric || !selectedInstance) return null;
    const metricQuery = currentMetric.query || '';
    const selectedInst = instances.find(
      (item) => item.instance_id === selectedInstance
    );
    if (!selectedInst) return null;
    const queryList = [
      {
        keys: currentMetric.instance_id_keys || [],
        values: selectedInst.instance_id_values,
      },
    ];
    let query = mergeViewQueryKeyValues(queryList);
    // 添加条件维度
    if (conditions?.length) {
      const conditionQueries = conditions
        .map((condition) => {
          if (condition.name && condition.method && condition.value) {
            return `${condition.name}${condition.method}"${condition.value}"`;
          }
          return '';
        })
        .filter(Boolean);
      if (conditionQueries.length) {
        if (query) {
          query += ',';
        }
        query += conditionQueries.join(',');
      }
    }

    // 基础查询语句（替换标签占位符）
    const baseQuery = metricQuery.replace(/__\$labels__/g, query);
    // 根据汇聚方式包装查询语句
    const finalQuery = wrapQueryWithAlgorithm(baseQuery);
    // 计算时间范围和步长
    // 基于汇聚周期计算：显示最近 N 个周期的数据（至少显示 50 个点）
    const periodInSeconds = getPeriodInSeconds();
    const MIN_POINTS = 50;
    const now = Date.now();
    // 时间范围：至少显示 50 个汇聚周期，最少 1 小时，最多 24 小时
    const minDuration = Math.max(periodInSeconds * MIN_POINTS * 1000, 3600000);
    const maxDuration = 86400000; // 24 小时
    const duration = Math.min(minDuration, maxDuration);
    const startTime = now - duration;
    const endTime = now;
    // step 设置为汇聚周期（秒）
    const step = periodInSeconds;

    return {
      query: finalQuery,
      source_unit: currentMetric.unit || '',
      unit: calculationUnit || '',
      start: startTime,
      end: endTime,
      step,
    };
  };

  const getInstances = async () => {
    // 取消之前的请求
    instanceAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    instanceAbortControllerRef.current = abortController;
    try {
      setInstanceLoading(true);
      const data = await getInstanceList(
        monitorObjId as React.Key,
        {
          page: 1,
          page_size: -1,
          name: '',
        },
        {
          signal: abortController.signal,
        }
      );
      const results = data?.results || [];
      setAllInstances(results);
    } catch (error: any) {
      if (error?.name !== 'AbortError') {
        setAllInstances([]);
      }
    } finally {
      if (!abortController.signal.aborted) {
        setInstanceLoading(false);
      }
    }
  };

  // 当 allInstances 加载完成后，更新 instances 中的 instance_name 和 instance_id_values
  useEffect(() => {
    if (allInstances.length === 0 || instances.length === 0) {
      return;
    }
    // source.values 和 allInstances.instance_id 格式一致，都是 "('1_os_172.18.0.17',)"
    // 需要从 allInstances 获取正确的 instance_id_values 用于查询
    const updatedInstances = instances.map((inst) => {
      const foundInstance = allInstances.find(
        (item) => item.instance_id === inst.instance_id
      );
      if (foundInstance) {
        const needsUpdate =
          foundInstance.instance_name !== inst.instance_name ||
          JSON.stringify(foundInstance.instance_id_values) !==
            JSON.stringify(inst.instance_id_values);
        if (needsUpdate) {
          return {
            ...inst,
            instance_name: foundInstance.instance_name || inst.instance_id,
            instance_id_values: foundInstance.instance_id_values || [
              inst.instance_id,
            ],
          };
        }
      }
      return inst;
    });
    // 检查是否有更新
    const hasUpdate = updatedInstances.some(
      (item, index) =>
        item.instance_name !== instances[index].instance_name ||
        JSON.stringify(item.instance_id_values) !==
          JSON.stringify(instances[index].instance_id_values)
    );
    if (hasUpdate) {
      setInstances(updatedInstances);
    }
  }, [allInstances, instances.length]);

  // 查询数据
  const fetchData = async () => {
    if (!canQuery) {
      setChartData([]);
      return;
    }
    const params = getQueryParams();
    if (!params) {
      setChartData([]);
      return;
    }
    // 取消之前的请求
    abortControllerRef.current?.abort();
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    const currentRequestId = ++requestIdRef.current;
    try {
      setLoading(true);
      const responseData = await get(
        '/monitor/api/metrics_instance/query_range/',
        {
          params,
          signal: abortController.signal,
        }
      );
      if (currentRequestId !== requestIdRef.current) {
        return;
      }
      const data = responseData.data?.result || [];
      const displayUnit = responseData.data?.unit || '';
      setUnit(displayUnit);
      // 渲染图表数据
      const selectedInst = instances.find(
        (item) => item.instance_id === selectedInstance
      );
      let list = [
        {
          instance_id_values: selectedInst.instance_id_values,
          instance_name: selectedInst.instance_name,
          instance_id: selectedInst.instance_id,
          instance_id_keys: currentMetric?.instance_id_keys || [],
          dimensions: currentMetric?.dimensions || [],
          title: currentMetric?.display_name || '--',
          showInstName: true,
        },
      ];
      if (!selectedInst) {
        list = [];
      }
      const _chartData = renderChart(data, list);
      setChartData(_chartData);
    } catch (error: any) {
      if (
        error?.name !== 'AbortError' &&
        currentRequestId === requestIdRef.current
      ) {
        setChartData([]);
      }
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  };

  // 监听依赖变化，自动重新查询
  useEffect(() => {
    fetchData();
    return () => {
      abortControllerRef.current?.abort();
    };
  }, [
    selectedInstance,
    metric,
    groupBy,
    conditions,
    period,
    periodUnit,
    algorithm,
    calculationUnit,
  ]);

  // 清理
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  // 处理实例选择变化
  const handleInstanceChange = (value: string) => {
    setSelectedInstance(value);
  };

  // 如果不满足显示条件，返回 null
  if (instances.length === 0 || !metric) {
    return null;
  }

  // 过滤掉空值的阈值
  const validThreshold = threshold.filter(
    (item) => item.value !== null && item.value !== undefined
  );

  const showUnit = (val) => {
    const unitName = findUnitNameById(val);
    return unitName ? `（${unitName}）` : '';
  };

  return (
    <div
      ref={previewRef}
      className="w-[600px] flex-shrink-0 sticky h-fit self-start border border-[var(--color-border-2)] rounded-md p-4 bg-[var(--color-bg-1)] transition-[top] duration-150"
      style={{ top: topOffset }}
    >
      {/* 标题和资产选择器 - 水平排列 */}
      <div className="flex items-center justify-between mb-3">
        <div className="font-medium text-[14px]">
          {t('monitor.events.metricPreview')}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[var(--color-text-3)] text-[12px]">
            {t('monitor.asset')}:
          </span>
          <Select
            className="w-[200px]"
            placeholder={t('monitor.events.index')}
            value={selectedInstance}
            loading={instanceLoading}
            onChange={handleInstanceChange}
            showSearch
            filterOption={(input, option) =>
              (option?.children as unknown as string)
                ?.toLowerCase()
                .includes(input.toLowerCase())
            }
          >
            {instances.map((item) => (
              <Option value={item.instance_id} key={item.instance_id}>
                {item.instance_name}
              </Option>
            ))}
          </Select>
        </div>
      </div>
      {/* 指标名称 */}
      {currentMetric && (
        <div className="text-[12px] text-[var(--color-text-2)] mb-2">
          {currentMetric.display_name || metric}
          {(calculationUnit || unit) && (
            <span className="text-[var(--color-text-3)] ml-1">
              {showUnit(calculationUnit || unit)}
            </span>
          )}
        </div>
      )}
      {/* 图表区域 */}
      <Spin spinning={loading}>
        <div className="h-[200px]">
          {chartData.length > 0 ? (
            <LineChart
              data={chartData}
              unit={unit}
              metric={currentMetric}
              threshold={validThreshold}
              allowSelect={false}
              showDimensionFilter={false}
            />
          ) : (
            <div className="h-full flex items-center justify-center">
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
            </div>
          )}
        </div>
      </Spin>
    </div>
  );
};

export default MetricPreview;
