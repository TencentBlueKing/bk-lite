'use client';

import { useEffect, useMemo, useState, type Key } from 'react';
import useViewApi from '@/app/monitor/api/view';
import type { TimeValuesProps } from '@/app/monitor/types';
import { buildSearchParams, runWithConcurrency } from '../../../shared/utils';
import { ES_INSTANT_QUERIES, ES_RANGE_QUERIES } from '../queries';
import { assembleElasticsearch, pendingElasticsearchView, type EsView } from './assemble';
import { freshWindowSeconds } from './model';
import {
  parseInstantSeries,
  parseRangeSeries,
  type InstantOutcome,
  type RangeOutcome
} from './wire';

const QUERY_CONCURRENCY = 4;
const FRESHNESS_CLOCK: TimeValuesProps = { timeRange: [], originValue: 1 };

interface UseElasticsearchProDataArgs {
  enabled: boolean;
  instanceReady: boolean;
  instanceId: Key;
  monitorObjectId: Key;
  idValues: string[];
  instanceIdKeys: string[];
  timeValues: TimeValuesProps;
  intervalSeconds?: number;
  loadTick: number;
  alertCount: number | null;
  alertPending: boolean;
}

export function useElasticsearchProData({
  enabled,
  instanceReady,
  instanceId,
  monitorObjectId,
  idValues,
  instanceIdKeys,
  timeValues,
  intervalSeconds,
  loadTick,
  alertCount,
  alertPending
}: UseElasticsearchProDataArgs): EsView {
  const { getInstanceQuery, getInstanceInstantQuery } = useViewApi();
  const [instant, setInstant] = useState<Record<string, InstantOutcome>>({});
  const [range, setRange] = useState<Record<string, RangeOutcome>>({});
  const [pending, setPending] = useState(true);
  const [nowSeconds, setNowSeconds] = useState(() => Date.now() / 1000);
  const idKey = idValues.join('\u0001');
  const keyList = instanceIdKeys.join('\u0001');
  const timeKey = `${timeValues.originValue ?? ''}|${timeValues.timeRange.join(',')}`;

  useEffect(() => {
    if (!enabled) return undefined;
    if (!instanceReady) {
      setPending(true);
      setInstant({});
      setRange({});
      return undefined;
    }
    if (!idValues.length || !monitorObjectId || !instanceId) {
      setPending(false);
      setInstant({});
      setRange({});
      return undefined;
    }
    let active = true;
    setPending(true);
    setInstant({});
    setRange({});
    const context = {
      monitorObjectId: String(monitorObjectId),
      instanceId: String(instanceId)
    };
    const values = idKey ? idKey.split('\u0001') : [];
    const keys = keyList ? keyList.split('\u0001') : [];
    const instantTasks = Object.entries(ES_INSTANT_QUERIES).map(([key, query]) => ({ key, query, instant: true as const }));
    const rangeTasks = Object.entries(ES_RANGE_QUERIES).map(([key, query]) => ({ key, query, instant: false as const }));
    const tasks = [...instantTasks, ...rangeTasks];
    const nextInstant: Record<string, InstantOutcome> = {};
    const nextRange: Record<string, RangeOutcome> = {};
    let newest = 0;
    runWithConcurrency(tasks, QUERY_CONCURRENCY, async (task) => {
      const params = buildSearchParams(
        task.query,
        'none',
        values,
        keys,
        task.instant ? FRESHNESS_CLOCK : timeValues,
        undefined,
        false,
        intervalSeconds,
        context
      );
      if (task.instant) {
        try {
          const result = await getInstanceInstantQuery(params);
          const series = parseInstantSeries(result);
          nextInstant[task.key] = { kind: 'ok', series };
          series.forEach((item) => {
            if (item.evalTime != null && item.evalTime > newest) newest = item.evalTime;
          });
        } catch {
          nextInstant[task.key] = { kind: 'error' };
        }
        return;
      }
      try {
        const result = await getInstanceQuery(params);
        nextRange[task.key] = { kind: 'ok', series: parseRangeSeries(result) };
      } catch {
        nextRange[task.key] = { kind: 'error' };
      }
    }).then(() => {
      if (!active) return;
      setInstant(nextInstant);
      setRange(nextRange);
      setNowSeconds(newest > 0 ? newest : Date.now() / 1000);
      setPending(false);
    });
    return () => {
      active = false;
    };
  }, [
    enabled,
    getInstanceInstantQuery,
    getInstanceQuery,
    idKey,
    instanceId,
    instanceReady,
    intervalSeconds,
    keyList,
    loadTick,
    monitorObjectId,
    timeKey,
    timeValues
  ]);

  return useMemo(() => {
    if (!enabled || !instanceReady || pending) return pendingElasticsearchView();
    return assembleElasticsearch({
      pending: false,
      hasInstance: idValues.length > 0,
      nowSeconds,
      freshSeconds: freshWindowSeconds(intervalSeconds),
      instant,
      range,
      alertCount,
      alertPending
    });
  }, [alertCount, alertPending, enabled, idValues.length, instant, instanceReady, intervalSeconds, nowSeconds, pending, range]);
}
