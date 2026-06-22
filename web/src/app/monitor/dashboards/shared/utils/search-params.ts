import { TimeValuesProps } from '@/app/monitor/types';
import { SearchParams } from '@/app/monitor/types/search';
import { getRecentTimeRange, mergeViewQueryKeyValues } from '@/app/monitor/utils/common';
import { calculateQueryStep } from '@/app/monitor/utils/queryStep';

export const buildSearchParams = (
  query: string,
  sourceUnit: string,
  idValues: string[],
  instanceIdKeys: string[],
  timeValues: TimeValuesProps,
  rawValueMetrics?: Set<string>,
  autoConvertUnit?: boolean,
  minStepSeconds?: unknown
): SearchParams => {
  const effectiveIdValues = idValues.length ? idValues : [''];
  const labels = mergeViewQueryKeyValues([
    { keys: instanceIdKeys.length ? instanceIdKeys : ['instance_id'], values: effectiveIdValues }
  ]);
  const recentTimeRange = getRecentTimeRange(timeValues);
  const startTime = recentTimeRange.at(0);
  const endTime = recentTimeRange.at(1);
  const resolvedAutoConvert = autoConvertUnit !== undefined
    ? autoConvertUnit
    : rawValueMetrics ? !Array.from(rawValueMetrics).some((m) => query.includes(m)) : true;
  const params: SearchParams = {
    query: query.replace(/__\$labels__/g, labels),
    source_unit: sourceUnit,
    auto_convert_unit: resolvedAutoConvert
  };

  if (Number.isFinite(startTime) && Number.isFinite(endTime)) {
    params.start = startTime;
    params.end = endTime;
    params.step = calculateQueryStep(params.start, params.end, minStepSeconds);
  }

  return params;
};
