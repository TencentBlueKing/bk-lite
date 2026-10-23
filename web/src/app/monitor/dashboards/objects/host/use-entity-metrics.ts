'use client';

import { useEffect, useRef, useState } from 'react';
import useViewApi from '@/app/monitor/api/view';
import type { TimeValuesProps } from '@/app/monitor/types';
import { buildSearchParams, runWithConcurrency } from '../../shared/utils';
import { parseRangeSeries, type LabeledSeries } from './entity-series';
import {
  entityQueryKeysToFetch,
  projectEntityLoad,
  type EntityLoadStatus
} from './entity-load-plan';
import type { HostEntityMetricQuery } from './queries';

export type { EntityLoadStatus };

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
  isDashboardMode: boolean;
  reloadKey?: number;
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
    isDashboardMode,
    reloadKey = 0
  } = options;
  const queriesRef = useRef(queries);
  queriesRef.current = queries;
  const idKey = JSON.stringify(idValues);
  const timeKey = JSON.stringify(timeValues);
  const instanceIdKey = instanceIdKeys.join(',');
  const queryKey = queries.map((item) => item.key).join(',');
  const identity = `${String(instanceId)}|${idKey}`;
  const [seenIdentity, setSeenIdentity] = useState(identity);
  const generationRef = useRef(0);
  const datasetRef = useRef('');
  const queryKeyRef = useRef(queryKey);
  const settledRef = useRef<Record<string, LabeledSeries[]>>({});
  const failedRef = useRef<Set<string>>(new Set());
  const inflightRef = useRef<Set<string>>(new Set());
  const previousTimeKeyRef = useRef(timeKey);
  const resetCache = (clearDataset: boolean) => {
    generationRef.current += 1;
    if (clearDataset) datasetRef.current = '';
    settledRef.current = {};
    failedRef.current = new Set();
    inflightRef.current = new Set();
  };
  if (identity !== seenIdentity) {
    setSeenIdentity(identity);
    setState(EMPTY);
    resetCache(true);
  }

  useEffect(() => {
    if (!idValues.length || !monitorObjectId || !instanceId) {
      resetCache(true);
      setState(EMPTY);
      return;
    }
    const dataset = `${identity}|${instanceIdKey}|${timeKey}|${String(minStepSeconds)}|${reloadKey}`;
    const datasetChanged = datasetRef.current !== dataset;
    const timeChanged = previousTimeKeyRef.current !== timeKey;
    previousTimeKeyRef.current = timeKey;
    if (datasetChanged) {
      datasetRef.current = dataset;
      generationRef.current += 1;
      settledRef.current = {};
      failedRef.current = new Set();
      inflightRef.current = new Set();
    }
    if (queryKeyRef.current !== queryKey) {
      queryKeyRef.current = queryKey;
      failedRef.current = new Set();
    }
    // 未激活的分类页签保留维度表。实例或时间变了就丢掉，避免切回来仍画旧窗。
    if (!enabled || !isDashboardMode) {
      if (datasetChanged) setState(EMPTY);
      return;
    }
    if (datasetChanged) {
      setState((prev) => ({
        status: 'loading',
        byMetric: timeChanged ? {} : prev.byMetric
      }));
    }
    const wanted = queriesRef.current;
    if (!wanted.length) {
      resetCache(false);
      setState(EMPTY);
      return;
    }
    const gen = generationRef.current;
    const publish = () => {
      if (generationRef.current !== gen) return;
      setState(projectEntityLoad(
        queriesRef.current.map((item) => item.key),
        settledRef.current,
        failedRef.current,
        inflightRef.current
      ));
    };
    const missingKeys = new Set(entityQueryKeysToFetch(
      wanted.map((item) => item.key),
      new Set(Object.keys(settledRef.current)),
      failedRef.current,
      inflightRef.current
    ));
    const missing = wanted.filter((item) => missingKeys.has(item.key));
    if (!missing.length) {
      publish();
      return;
    }
    missing.forEach((item) => inflightRef.current.add(item.key));
    setState((prev) => (prev.status === 'loading' ? prev : { ...prev, status: 'loading' }));
    void runWithConcurrency(missing, 4, async (query) => {
      let series: LabeledSeries[] | null = null;
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
        series = parseRangeSeries(raw);
      } catch {
        series = null;
      }
      if (generationRef.current !== gen) return;
      if (series) settledRef.current[query.key] = series;
      else failedRef.current.add(query.key);
      inflightRef.current.delete(query.key);
    }).then(() => {
      publish();
    });
    // idValues 由 idKey / identity 锁定；query 引用用 ref，避免 hook 返回新函数导致重复请求。
    // reloadKey 由专业盘刷新传入，dataset 变化会清空缓存并重拉。queryKey 变化只补缺失 key。
  }, [enabled, isDashboardMode, identity, idKey, instanceIdKey, timeKey, queryKey, monitorObjectId, instanceId, minStepSeconds, reloadKey]);

  return state;
}
