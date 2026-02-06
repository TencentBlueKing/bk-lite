'use client';
import React, { useState, useCallback } from 'react';
import { Tooltip, Spin } from 'antd';
import { UnorderedListOutlined } from '@ant-design/icons';
import useViewApi from '@/app/monitor/api/view';
import { useTranslation } from '@/utils/i18n';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';
import {
  TooltipMetricDataItem,
  TooltipDimensionDataItem,
  MetricDimensionTooltipProps
} from '@/app/monitor/types/view';

const MetricDimensionTooltip: React.FC<MetricDimensionTooltipProps> = ({
  instanceId,
  metricId,
  monitorObjectId,
  metricItem
}) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState<boolean>(false);
  const [dimensionData, setDimensionData] = useState<
    TooltipDimensionDataItem[]
  >([]);
  const { getMetricsInstanceQuery } = useViewApi();
  const { getEnumValueUnit } = useUnitTransform();

  const dimensions = metricItem?.dimensions || [];

  const formatMetricData = useCallback(
    (
      metricsData: TooltipMetricDataItem[],
      unit: string
    ): TooltipDimensionDataItem[] => {
      if (!metricsData?.length || !dimensions?.length) {
        return [];
      }
      return metricsData.map((item) => {
        const metric = item.metric;
        const rawValue = item.value[1];
        const value = getEnumValueUnit({ ...metricItem, unit }, rawValue);
        const dimensionParts = dimensions
          .map((dim) => {
            const dimValue = metric[dim.name];
            if (dimValue !== undefined) {
              return `${dim.description || dim.name}: ${dimValue}`;
            }
            return null;
          })
          .filter(Boolean);
        const label = [dimensionParts.join('-')].filter(Boolean).join('');
        return {
          label,
          value
        };
      });
    },
    [dimensions, metricItem, getEnumValueUnit]
  );

  const fetchDimensionData = useCallback(async () => {
    setLoading(true);
    try {
      const responseData = await getMetricsInstanceQuery({
        monitor_object_id: monitorObjectId,
        instance_id: instanceId,
        metric_id: metricId,
        auto_convert: false
      });
      const data = responseData?.data || {};
      const formattedData = formatMetricData(data.result || [], data.unit);
      setDimensionData(formattedData);
    } catch {
      setDimensionData([]);
    } finally {
      setLoading(false);
    }
  }, [
    instanceId,
    metricId,
    monitorObjectId,
    getMetricsInstanceQuery,
    formatMetricData
  ]);

  const handleOpenChange = (open: boolean) => {
    if (open) {
      fetchDimensionData();
    }
  };

  const tooltipContent = (
    <div className="min-w-[200px]">
      {loading ? (
        <div className="flex justify-center items-center py-[20px]">
          <Spin size="small" />
        </div>
      ) : dimensionData.length > 0 ? (
        <div className="flex flex-col gap-[8px]">
          {dimensionData.map((item, index) => (
            <div
              key={index}
              className="flex justify-between items-start gap-[16px] whitespace-nowrap"
            >
              <span>{item.label}</span>
              <span className="font-medium">{item.value}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center text-[var(--color-text-3)] py-[10px]">
          {t('common.noResult')}
        </div>
      )}
    </div>
  );

  return (
    <>
      <style>{`
        .metric-dimension-tooltip.ant-tooltip {
          max-width: none;
        }
      `}</style>
      <Tooltip
        title={tooltipContent}
        placement="left"
        trigger="hover"
        overlayClassName="metric-dimension-tooltip"
        onOpenChange={handleOpenChange}
      >
        <UnorderedListOutlined className="text-[var(--color-text-3)] hover:text-[var(--color-primary)] cursor-pointer ml-[8px]" />
      </Tooltip>
    </>
  );
};

export default MetricDimensionTooltip;
