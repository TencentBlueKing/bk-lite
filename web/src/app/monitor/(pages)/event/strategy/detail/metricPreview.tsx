'use client';
import React, { useState, useEffect, useRef, useMemo, RefObject } from 'react';
import { Select, Spin, Empty } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useMonitorApi from '@/app/monitor/api';
import useEventApi from '@/app/monitor/api/event';
import LineChart from '@/app/monitor/components/charts/lineChart';
import {
  ChartData,
  MetricItem,
  ThresholdField,
  FilterItem,
  TableDataItem
} from '@/app/monitor/types';
import { SourceFeild } from '@/app/monitor/types/event';
import { InstanceItem } from '@/app/monitor/types/search';
import { renderChart } from '@/app/monitor/utils/common';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';
import { sanitizeGroupBy } from '@/app/monitor/utils/metricDimensions';

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
  fixedGroupByList?: string[];
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
  fixedGroupByList = []
}) => {
  const { t } = useTranslation();
  const { getInstanceList } = useMonitorApi();
  const { previewMonitorPolicy } = useEventApi();
  const { findUnitNameById } = useUnitTransform();
  const [loading, setLoading] = useState<boolean>(false);
  const [instanceLoading, setInstanceLoading] = useState<boolean>(false);
  const [chartData, setChartData] = useState<ChartData[]>([]);
  const [unit, setUnit] = useState<string>('');
  const [previewError, setPreviewError] = useState<string>('');
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
    // 当 allInstances 已加载时，直接使用其中的名称信息
    const instanceItems: InstanceItem[] = source.values.map((val: string) => {
      const foundInstance = allInstances.find(
        (item) => item.instance_id === val
      );
      return {
        instance_id: val,
        instance_name: foundInstance?.instance_name || val,
        instance_id_values: foundInstance?.instance_id_values || [val]
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
  }, [source?.type, source?.values, allInstances]);

  // 判断是否可以查询
  const canQuery = useMemo(() => {
    const sanitizedGroupBy = sanitizeGroupBy(groupBy);
    return !!(
      monitorObjId &&
      metric &&
      algorithm &&
      sanitizedGroupBy.length > 0 &&
      selectedInstance &&
      instances.length > 0
    );
  }, [monitorObjId, metric, algorithm, groupBy.length, selectedInstance, instances.length]);

  // 获取当前选中的指标信息
  const currentMetric = useMemo(() => {
    return metrics.find((item) => item.name === metric);
  }, [metrics, metric]);

  // 构建后端策略预览参数，PromQL 由后端统一构造
  const getPreviewPayload = () => {
    if (!currentMetric || !selectedInstance) return null;
    const selectedInst = instances.find(
      (item) => item.instance_id === selectedInstance
    );
    if (!selectedInst) return null;
    const filter = (conditions || []).filter(
      (condition) => condition.name && condition.method && condition.value
    );
    const sanitizedGroupBy = sanitizeGroupBy(groupBy);
    return {
      monitor_object: monitorObjId,
      query_condition: {
        type: 'metric',
        metric_id: currentMetric.id,
        filter
      },
      source,
      period: {
        type: periodUnit,
        value: period || 5
      },
      algorithm,
      group_by: sanitizedGroupBy,
      metric_unit: currentMetric.unit || '',
      calculation_unit: calculationUnit || '',
      preview: {
        instance_id: selectedInst.instance_id,
        instance_id_values: selectedInst.instance_id_values,
        duration_points: 30
      }
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
          name: ''
        },
        {
          signal: abortController.signal
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

  // 查询数据
  const fetchData = async () => {
    if (!canQuery) {
      setChartData([]);
      setPreviewError('');
      return;
    }
    const payload = getPreviewPayload();
    if (!payload) {
      setChartData([]);
      setPreviewError('');
      return;
    }
    // 取消之前的请求
    abortControllerRef.current?.abort();
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    const currentRequestId = ++requestIdRef.current;
    try {
      setLoading(true);
      setPreviewError('');
      const responseData = await previewMonitorPolicy(payload, {
        signal: abortController.signal
      });
      if (currentRequestId !== requestIdRef.current) {
        return;
      }
      const vmData = responseData?.data || {};
      const data = vmData.data?.result || [];
      const displayUnit = vmData.unit || '';
      setUnit(displayUnit);
      // 渲染图表数据
      const selectedInst = instances.find(
        (item) => item.instance_id === selectedInstance
      );
      // 判断 showInstName：groupBy 为空或 groupBy 的值都在固定列表中时为 true
      const sanitizedGroupBy = sanitizeGroupBy(groupBy);
      const showInstName = sanitizedGroupBy.some((item) =>
        fixedGroupByList.includes(item)
      );
      let list = [];
      if (selectedInst) {
        list = [
          {
            instance_id_values: selectedInst.instance_id_values,
            instance_name: selectedInst.instance_name,
            instance_id: selectedInst.instance_id,
            instance_id_keys: currentMetric?.instance_id_keys || [],
            dimensions: currentMetric?.dimensions || [],
            title: currentMetric?.display_name || '--',
            showInstName
          }
        ];
      }
      const _chartData = renderChart(data, list);
      setChartData(_chartData);
    } catch (error: any) {
      if (
        error?.name !== 'AbortError' &&
        currentRequestId === requestIdRef.current
      ) {
        setChartData([]);
        setPreviewError(
          error?.response?.data?.message ||
            error?.message ||
            t('common.error')
        );
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
    instances,
    metric,
    groupBy,
    conditions,
    period,
    periodUnit,
    algorithm,
    calculationUnit
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
      className="w-full sticky h-fit self-start border border-[var(--color-border-2)] rounded-md p-4 bg-[var(--color-bg-1)] shadow-md transition-[top] duration-150"
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
          {previewError ? (
            <div className="h-full flex items-center justify-center text-[12px] text-[var(--color-text-3)] px-4 text-center">
              {previewError}
            </div>
          ) : chartData.length > 0 ? (
            <LineChart
              data={chartData}
              unit={calculationUnit || unit}
              metric={currentMetric}
              threshold={validThreshold}
              allowSelect={false}
              showDimensionFilter={true}
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
