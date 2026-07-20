'use client';
import React, { useState, useEffect, useRef, useMemo, RefObject } from 'react';
import { Select, Spin, Empty, Alert } from 'antd';
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
import { MetricExpressionRow } from './metricExpressionTypes';
import {
  buildMetricExpressionPreviewPayload,
  MetricExpressionMode
} from './formulaExpressionUtils';
import { resolvePreviewChartUnit } from './strategyDetailUtils';

const { Option } = Select;

interface MetricPreviewProps {
  monitorObjId: string | null;
  source: SourceFeild;
  metric: string | null;
  metrics: MetricItem[];
  groupBy: string[];
  groupAlgorithm: string | null;
  conditions: FilterItem[];
  period: number | null;
  periodUnit: string;
  algorithm: string | null;
  threshold: ThresholdField[];
  calculationUnit?: string | null;
  thresholdUnit?: string | null;
  metricRows: MetricExpressionRow[];
  metricExpressionMode: MetricExpressionMode;
  resultName: string;
  expression: string;
  scrollContainerRef?: RefObject<HTMLDivElement | null>;
  anchorRef?: RefObject<HTMLDivElement | null>;
  fixedGroupByList?: string[];
}

const normalizePreviewWarnings = (warnings: unknown): string[] => {
  if (!Array.isArray(warnings)) {
    return [];
  }

  return warnings
    .map((item) => {
      if (typeof item === 'string') {
        return item;
      }
      if (item && typeof item === 'object') {
        const record = item as Record<string, unknown>;
        const message = record.message || record.detail || record.code;
        return typeof message === 'string' ? message : JSON.stringify(record);
      }
      return '';
    })
    .filter(Boolean);
};

const MetricPreview: React.FC<MetricPreviewProps> = ({
  monitorObjId,
  source,
  metric,
  metrics,
  groupBy,
  groupAlgorithm,
  conditions,
  period,
  periodUnit,
  algorithm,
  threshold,
  calculationUnit,
  thresholdUnit,
  metricRows,
  metricExpressionMode,
  resultName,
  expression,
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
  const [previewChartUnit, setPreviewChartUnit] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string>('');
  const [previewWarnings, setPreviewWarnings] = useState<string[]>([]);
  const [previewThreshold, setPreviewThreshold] = useState<ThresholdField[]>([]);
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
    const previewGroupBy =
      metricExpressionMode === 'formula'
        ? sanitizeGroupBy(metricRows[0]?.groupBy || [])
        : sanitizeGroupBy(groupBy);
    const hasMetricExpression =
      metricExpressionMode === 'formula' ? metricRows.length > 0 : !!metric;
    return !!(
      monitorObjId &&
      hasMetricExpression &&
      algorithm &&
      previewGroupBy.length > 0 &&
      selectedInstance &&
      instances.length > 0
    );
  }, [
    monitorObjId,
    metric,
    metricRows,
    metricExpressionMode,
    algorithm,
    groupBy,
    selectedInstance,
    instances.length
  ]);

  // 获取当前选中的指标信息
  const currentMetric = useMemo(() => {
    const anchorRow = metricRows[0];
    if (anchorRow?.metricId || anchorRow?.metricName) {
      return metrics.find(
        (item) =>
          item.id === anchorRow.metricId || item.name === anchorRow.metricName
      );
    }
    return metrics.find((item) => item.name === metric);
  }, [metrics, metric, metricRows]);

  // 构建后端策略预览参数，PromQL 由后端统一构造
  const getPreviewPayload = () => {
    if (!selectedInstance) return null;
    const selectedInst = instances.find(
      (item) => item.instance_id === selectedInstance
    );
    if (!selectedInst) return null;
    return buildMetricExpressionPreviewPayload({
      monitorObjId,
      source,
      metrics,
      mode: metricExpressionMode,
      resultName,
      expression,
      rows: metricRows,
      selectedInstance: selectedInst,
      period,
      periodUnit,
      algorithm,
      groupAlgorithm,
      groupBy,
      threshold,
      calculationUnit,
      thresholdUnit
    });
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
      setPreviewWarnings([]);
      setPreviewThreshold([]);
      setPreviewChartUnit(null);
      return;
    }
    let payload = null;
    try {
      payload = getPreviewPayload();
    } catch (error) {
      setChartData([]);
      setPreviewWarnings([]);
      setPreviewThreshold([]);
      setPreviewChartUnit(null);
      setPreviewError(
        error instanceof Error
          ? error.message
          : t('monitor.events.metricValidate')
      );
      return;
    }
    if (!payload) {
      setChartData([]);
      setPreviewError('');
      setPreviewWarnings([]);
      setPreviewThreshold([]);
      setPreviewChartUnit(null);
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
      setPreviewWarnings([]);
      const responseData = await previewMonitorPolicy(payload, {
        signal: abortController.signal
      });
      if (currentRequestId !== requestIdRef.current) {
        return;
      }
      const vmData = responseData?.data || {};
      const data = vmData.data?.result || [];
      setPreviewWarnings(
        normalizePreviewWarnings(responseData?.warnings || vmData.warnings)
      );
      setPreviewThreshold(
        Array.isArray(responseData?.threshold) ? responseData.threshold : []
      );
      setPreviewChartUnit(
        resolvePreviewChartUnit(
          responseData?.chart_unit,
          thresholdUnit,
          calculationUnit
        )
      );
      // 渲染图表数据
      const selectedInst = instances.find(
        (item) => item.instance_id === selectedInstance
      );
      // 判断 showInstName：groupBy 为空或 groupBy 的值都在固定列表中时为 true
      const sanitizedGroupBy =
        metricExpressionMode === 'formula'
          ? sanitizeGroupBy(metricRows[0]?.groupBy || [])
          : sanitizeGroupBy(groupBy);
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
            title:
              metricExpressionMode === 'formula'
                ? resultName || currentMetric?.display_name || '--'
                : currentMetric?.display_name || '--',
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
        setPreviewWarnings([]);
        setPreviewThreshold([]);
        setPreviewChartUnit(null);
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
    metrics,
    metric,
    groupBy,
    conditions,
    period,
    periodUnit,
    groupAlgorithm,
    algorithm,
    threshold,
    calculationUnit,
    thresholdUnit,
    metricRows,
    metricExpressionMode,
    resultName,
    expression
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
  if (
    instances.length === 0 ||
    (metricExpressionMode !== 'formula' && !metric)
  ) {
    return null;
  }

  // 过滤掉空值的阈值
  const validThreshold = previewThreshold.filter(
    (item) => item.value !== null && item.value !== undefined
  );
  const effectiveChartUnit = resolvePreviewChartUnit(
    previewChartUnit,
    thresholdUnit,
    calculationUnit
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
          {metricExpressionMode === 'formula'
            ? resultName || currentMetric.display_name || metric
            : currentMetric.display_name || metric}
          {effectiveChartUnit && (
            <span className="text-[var(--color-text-3)] ml-1">
              {showUnit(effectiveChartUnit)}
            </span>
          )}
        </div>
      )}
      {previewWarnings.length > 0 && (
        <Alert
          className="mb-2 text-[12px]"
          type="warning"
          showIcon
          message={previewWarnings.join('；')}
        />
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
              unit={effectiveChartUnit}
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
