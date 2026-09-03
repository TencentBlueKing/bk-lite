import { TimeValuesProps } from '@/app/monitor/types';
import { SearchParams } from '@/app/monitor/types/search';
import { getRecentTimeRange } from '@/app/monitor/utils/common';
import { buildGapDetectionParams } from '@/app/monitor/utils/gapIntervals';
import { calculateQueryStep } from '@/app/monitor/utils/queryStep';
import type { Key } from 'react';
import { dashboardQueryCapabilityId } from './query-capability';

interface DashboardQueryContext {
  monitorObjectId: Key;
  instanceId: Key;
}

interface DynamicCapabilityParams {
  capabilityId: string;
  capabilityParams: Record<string, unknown>;
  sourceUnit: string;
  timeValues: TimeValuesProps;
  minStepSeconds?: unknown;
  context: DashboardQueryContext;
}

const applyTimeRange = (
  params: SearchParams,
  timeValues: TimeValuesProps,
  minStepSeconds?: unknown,
) => {
  const recentTimeRange = getRecentTimeRange(timeValues);
  const startTime = recentTimeRange.at(0);
  const endTime = recentTimeRange.at(1);
  if (Number.isFinite(startTime) && Number.isFinite(endTime)) {
    params.start = startTime;
    params.end = endTime;
    params.time = endTime;
    params.step = calculateQueryStep(params.start, params.end, minStepSeconds);
  }
  return buildGapDetectionParams(params, minStepSeconds);
};

export const buildDynamicCapabilitySearchParams = ({
  capabilityId,
  capabilityParams,
  sourceUnit,
  timeValues,
  minStepSeconds,
  context,
}: DynamicCapabilityParams): SearchParams => applyTimeRange({
  capability_id: capabilityId,
  capability_params: capabilityParams,
  monitor_object_id: context.monitorObjectId,
  instance_ids: [String(context.instanceId)],
  source_unit: sourceUnit,
  auto_convert_unit: false,
}, timeValues, minStepSeconds);

export const buildSearchParams = (
  query: string,
  sourceUnit: string,
  _idValues: string[],
  _instanceIdKeys: string[],
  timeValues: TimeValuesProps,
  rawValueMetrics: Set<string> | undefined,
  autoConvertUnit: boolean | undefined,
  minStepSeconds: unknown,
  context: DashboardQueryContext,
): SearchParams => {
  // 仪表盘按声明单位由前端 formatMetricValue。省略 autoConvertUnit 且未传 rawValueMetrics 时默认 false，
  // 避免服务端先缩成 hour/GiB 再按原单位展示。显式 true 仍可用于会读响应 data.unit 的调用方。
  // 传入 rawValueMetrics 时：命中白名单的 query 关闭自动换算，其余仍为 true。
  const resolvedAutoConvert = autoConvertUnit !== undefined
    ? autoConvertUnit
    : rawValueMetrics ? !Array.from(rawValueMetrics).some((m) => query.includes(m)) : false;
  const params: SearchParams = {
    capability_id: dashboardQueryCapabilityId(query),
    monitor_object_id: context.monitorObjectId,
    instance_ids: [String(context.instanceId)],
    source_unit: sourceUnit,
    auto_convert_unit: resolvedAutoConvert
  };

  return applyTimeRange(params, timeValues, minStepSeconds);
};
