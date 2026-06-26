import React from 'react';
import { ChartData, MetricItem } from '@/app/monitor/types';
import { renderChart } from '@/app/monitor/utils/common';
import { attachGapIntervals } from '@/app/monitor/utils/gapIntervals';
import { BaseMetricConfig, MetricSeriesBase } from '../types';

export const toMetricSeries = <T extends BaseMetricConfig>(
  metric: T,
  result: any,
  instanceId: React.Key,
  instanceName: string,
  idValues: string[],
  instanceIdKeys: string[]
): T & { viewData: ChartData[]; loadState: 'success' } => {
  const viewData = attachGapIntervals(
    renderChart(result?.data?.result || [], [
      {
        instance_id_values: idValues,
        instance_name: instanceName,
        instance_id: String(instanceId || ''),
        instance_id_keys: instanceIdKeys,
        dimensions: metric.dimensions || [],
        title: metric.display_name
      }
    ]),
    result?.data?.gaps || []
  );

  return { ...metric, viewData, loadState: 'success' as const };
};

export const buildMetricItem = (metric: MetricSeriesBase | BaseMetricConfig): MetricItem => ({
  id: 0,
  metric_group: 0,
  metric_object: 0,
  name: metric.name,
  type: 'number',
  display_name: metric.display_name,
  dimensions: metric.dimensions || [],
  unit: metric.unit,
  query: metric.query,
  description: metric.description,
  color: metric.color,
  viewData: 'viewData' in metric ? metric.viewData : []
});
