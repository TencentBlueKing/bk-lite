'use client';

import { useEffect, useRef, useState } from 'react';
import useViewApi from '@/app/monitor/api/view';
import type { TimeValuesProps } from '@/app/monitor/types';
import { buildSearchParams, runWithConcurrency } from '../../shared/utils';
import { parseRangeSeries, type LabeledSeries } from './entity-series';
import type { HostEntityMetricQuery } from './queries';

export type EntityLoadStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'error';

export interface EntityLoadState {
  status: EntityLoadStatus;
  byMetric: Record<string, LabeledSeries[]>;
}

const EMPTY: EntityLoadState = { status: 'idle', byMetric: {} };

export function useHostEntityMetrics(options: {
  enabled: boolean;
  queries: HostEntityMetricQuery[];
  idValues: string[];
  instanceIdKeys: string[];
  timeValues: TimeValuesProps;
  monitorObjectId: React.Key;
  instanceId: React.Key;
  minStepSeconds?: unknown;
  loadTick: number;
  isDashboardMode: boolean;
}): EntityLoadState {
  const { getInstanceQuery } = useViewApi();
  const queryRef = useRef(getInstanceQuery);
  queryRef.current = getInstanceQuery;
  const [state, setState] = useState<EntityLoadState>(EMPTY);
  const {
    enabled,
    queries,
    idValues,
    instanceIdKeys,
    timeValues,
    monitorObjectId,
    instanceId,
    minStepSeconds,
    loadTick,
    isDashboardMode
  } = options;
  const idKey = JSON.stringify(idValues);
  const timeKey = JSON.stringify(timeValues);
  const queryKey = queries.map((item) => item.key).join(',');

  useEffect(() => {
    if (!enabled || !isDashboardMode || !idValues.length || !monitorObjectId || !instanceId) {
      setState(EMPTY);
      return;
    }
    let active = true;
    setState((prev) => ({ ...prev, status: 'loading' }));
    runWithConcurrency(queries, 4, async (query) => {
      try {
        const raw = await queryRef.current(
          buildSearchParams(
            query.query,
            query.unit,
            idValues,
            instanceIdKeys,
            timeValues,
            undefined,
            false,
            minStepSeconds,
            { monitorObjectId, instanceId }
          )
        );
        return [query.key, parseRangeSeries(raw)] as const;
      } catch {
        return [query.key, null] as const;
      }
    }).then((entries) => {
      if (!active) return;
      const failed = entries.every(([, series]) => series == null);
      const byMetric: Record<string, LabeledSeries[]> = {};
      entries.forEach(([key, series]) => {
        if (series) byMetric[key] = series;
      });
      const anySeries = Object.values(byMetric).some((series) => series.length > 0);
      setState({
        status: failed ? 'error' : anySeries ? 'ready' : 'empty',
        byMetric
      });
    });
    return () => {
      active = false;
    };
    // idValues 由 idKey 锁定；query 引用用 ref，避免 hook 返回新函数导致重复请求。
  }, [enabled, isDashboardMode, idKey, timeKey, queryKey, monitorObjectId, instanceId, minStepSeconds, loadTick]);

  return state;
}
