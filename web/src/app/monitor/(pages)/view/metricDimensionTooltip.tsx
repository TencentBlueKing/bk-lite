'use client';
import React, { useState, useCallback } from 'react';
import { Tooltip, Spin, Button } from 'antd';
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
  monitorObjectId,
  metricInfo
}) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState<boolean>(false);
  const [dimensionData, setDimensionData] = useState<
    TooltipDimensionDataItem[]
  >([]);
  const [truncated, setTruncated] = useState(false);
  const [previewLimit, setPreviewLimit] = useState<number | ''>('');
  const { getMetricsInstanceQuery } = useViewApi();
  const { getEnumValueUnit } = useUnitTransform();

  const { metricItem, metricUnit } = metricInfo;
  const metricId = metricItem?.id;
  const dimensions = metricItem?.dimensions || [];

  const formatMetricData = useCallback(
    (metricsData: TooltipMetricDataItem[]): TooltipDimensionDataItem[] => {
      if (!metricsData?.length || !dimensions?.length) {
        return [];
      }
      return metricsData.map((item) => {
        const metric = item.metric;
        const rawValue = item.value[1];
        const value = getEnumValueUnit(metricItem, rawValue, metricUnit);
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
    [dimensions, metricItem, metricUnit, getEnumValueUnit]
  );

  const openFullDetails = useCallback(() => {
    const params = new URLSearchParams({
      monitor_object: String(monitorObjectId),
      instance_id: String(instanceId),
      metric_id: String(metricId || metricItem?.name || '')
    });
    window.open(
      `/monitor/search?${params.toString()}`,
      '_blank',
      'noopener,noreferrer'
    );
  }, [instanceId, metricId, metricItem?.name, monitorObjectId]);

  const fetchDimensionData = useCallback(async () => {
    setLoading(true);
    try {
      // 不传 limit/mode：后端按通用 CARD_QUERY_MAX_SERIES + limitk 截断。
      const responseData = await getMetricsInstanceQuery({
        monitor_object_id: monitorObjectId,
        instance_id: instanceId,
        metric_id: metricId,
        auto_convert: false
      });
      const data = responseData?.data || {};
      const formattedData = formatMetricData(data.result || []);
      setDimensionData(formattedData);
      setPreviewLimit(data.series_budget?.limit ?? '');
      setTruncated(Boolean(data.series_budget?.truncated));
    } catch {
      setDimensionData([]);
      setTruncated(false);
      setPreviewLimit('');
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
    <div className="min-w-[200px] max-w-[420px]">
      {loading ? (
        <div className="flex justify-center items-center py-[20px]">
          <Spin size="small" />
        </div>
      ) : dimensionData.length > 0 ? (
        <div className="flex flex-col gap-[8px]">
          <div className="max-h-[280px] overflow-y-auto flex flex-col gap-[8px] pr-[4px]">
            {dimensionData.map((item, index) => (
              <div
                key={index}
                className="flex justify-between items-start gap-[16px] whitespace-nowrap"
              >
                <span className="truncate max-w-[280px]" title={item.label}>
                  {item.label}
                </span>
                <span className="font-medium shrink-0">{item.value}</span>
              </div>
            ))}
          </div>
          {truncated ? (
            <div className="pt-[4px] border-t border-[var(--color-border-1)] flex items-center justify-between gap-[8px]">
              <span className="text-[12px] text-[var(--color-text-3)]">
                {t('monitor.views.dimensionPreviewTruncated', '', {
                  limit: previewLimit
                })}
              </span>
              <Button type="link" size="small" className="px-0" onClick={openFullDetails}>
                {t('monitor.views.dimensionPreviewMore')}
              </Button>
            </div>
          ) : null}
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
