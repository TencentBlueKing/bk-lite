'use client';

import { useEffect, useRef, useState, type Key } from 'react';
import useViewApi from '@/app/monitor/api/view';
import type { TimeValuesProps } from '@/app/monitor/types';
import { buildSearchParams, runWithConcurrency } from '../../../shared/utils';
import { DOCKER_PRO_QUERY } from './queries';
import { freshWindowSec, type Probe } from './reading';
import { readInstantSamples, readNamedSeries, type NamedSeries } from './samples';
import { buildDockerProView, emptyProbe, type DockerProView } from './view';

interface DockerProArgs {
  instanceId: Key;
  monitorObjectId: Key;
  idValues: string[];
  instanceIdKeys: string[];
  timeValues: TimeValuesProps;
  intervalSec?: number;
  reloadKey: number;
}

export type DockerProState =
  | { phase: 'loading'; view: null }
  | { phase: 'ready'; view: DockerProView };

type InstantKey =
  | 'runningValue'
  | 'runningTime'
  | 'runningCapability'
  | 'stoppedValue'
  | 'stoppedTime'
  | 'stoppedCapability'
  | 'totalValue'
  | 'totalTime'
  | 'totalCapability'
  | 'cpuValue'
  | 'cpuTime'
  | 'cpuCapability'
  | 'memPercentValue'
  | 'memPercentTime'
  | 'memPercentCapability'
  | 'memBytesValue'
  | 'memBytesTime'
  | 'memBytesCapability'
  | 'restartValue'
  | 'restartTime';

type RangeKey = 'cpuChart' | 'memPercentChart' | 'memBytesChart';

interface InstantJob {
  key: InstantKey;
  query: string;
  unit: string;
}

interface RangeJob {
  key: RangeKey;
  query: string;
  unit: string;
}

const INSTANT_JOBS: InstantJob[] = [
  { key: 'runningValue', query: DOCKER_PRO_QUERY.runningValue, unit: 'counts' },
  { key: 'runningTime', query: DOCKER_PRO_QUERY.runningTime, unit: 'none' },
  { key: 'runningCapability', query: DOCKER_PRO_QUERY.runningCapability, unit: 'none' },
  { key: 'stoppedValue', query: DOCKER_PRO_QUERY.stoppedValue, unit: 'counts' },
  { key: 'stoppedTime', query: DOCKER_PRO_QUERY.stoppedTime, unit: 'none' },
  { key: 'stoppedCapability', query: DOCKER_PRO_QUERY.stoppedCapability, unit: 'none' },
  { key: 'totalValue', query: DOCKER_PRO_QUERY.totalValue, unit: 'counts' },
  { key: 'totalTime', query: DOCKER_PRO_QUERY.totalTime, unit: 'none' },
  { key: 'totalCapability', query: DOCKER_PRO_QUERY.totalCapability, unit: 'none' },
  { key: 'cpuValue', query: DOCKER_PRO_QUERY.cpuValue, unit: 'percent' },
  { key: 'cpuTime', query: DOCKER_PRO_QUERY.cpuTime, unit: 'none' },
  { key: 'cpuCapability', query: DOCKER_PRO_QUERY.cpuCapability, unit: 'none' },
  { key: 'memPercentValue', query: DOCKER_PRO_QUERY.memPercentValue, unit: 'percent' },
  { key: 'memPercentTime', query: DOCKER_PRO_QUERY.memPercentTime, unit: 'none' },
  { key: 'memPercentCapability', query: DOCKER_PRO_QUERY.memPercentCapability, unit: 'none' },
  { key: 'memBytesValue', query: DOCKER_PRO_QUERY.memBytesValue, unit: 'bytes' },
  { key: 'memBytesTime', query: DOCKER_PRO_QUERY.memBytesTime, unit: 'none' },
  { key: 'memBytesCapability', query: DOCKER_PRO_QUERY.memBytesCapability, unit: 'none' },
  { key: 'restartValue', query: DOCKER_PRO_QUERY.restartValue, unit: 'counts' },
  { key: 'restartTime', query: DOCKER_PRO_QUERY.restartTime, unit: 'none' }
];

const RANGE_JOBS: RangeJob[] = [
  { key: 'cpuChart', query: DOCKER_PRO_QUERY.cpuChart, unit: 'percent' },
  { key: 'memPercentChart', query: DOCKER_PRO_QUERY.memPercentChart, unit: 'percent' },
  { key: 'memBytesChart', query: DOCKER_PRO_QUERY.memBytesChart, unit: 'bytes' }
];

const scopeKey = (args: DockerProArgs): string => [
  String(args.instanceId || ''),
  String(args.monitorObjectId || ''),
  args.idValues.join('\u0001'),
  args.instanceIdKeys.join('\u0001'),
  String(args.intervalSec ?? ''),
  String(args.reloadKey),
  String(args.timeValues.originValue ?? ''),
  (args.timeValues.timeRange || []).join(',')
].join('|');

const blankState = (scope: string): DockerProState & { scope: string } => ({
  phase: 'ready',
  scope,
  view: buildDockerProView({
    hasInstance: false,
    freshSec: freshWindowSec(undefined),
    runningValue: emptyProbe(),
    runningTime: emptyProbe(),
    runningCapability: emptyProbe(),
    stoppedValue: emptyProbe(),
    stoppedTime: emptyProbe(),
    stoppedCapability: emptyProbe(),
    totalValue: emptyProbe(),
    totalTime: emptyProbe(),
    totalCapability: emptyProbe(),
    cpuValue: emptyProbe(),
    cpuTime: emptyProbe(),
    cpuCapability: emptyProbe(),
    cpuChart: [],
    memPercentValue: emptyProbe(),
    memPercentTime: emptyProbe(),
    memPercentCapability: emptyProbe(),
    memPercentChart: [],
    memBytesValue: emptyProbe(),
    memBytesTime: emptyProbe(),
    memBytesCapability: emptyProbe(),
    memBytesChart: [],
    restartValue: emptyProbe(),
    restartTime: emptyProbe()
  })
});

export function useDockerPro(args: DockerProArgs): DockerProState {
  const { getInstanceQuery, getInstanceInstantQuery } = useViewApi();
  const scope = scopeKey(args);
  const argsRef = useRef(args);
  argsRef.current = args;
  const [state, setState] = useState<DockerProState & { scope: string }>(() => ({
    phase: 'loading',
    view: null,
    scope
  }));
  if (state.scope !== scope) {
    setState({ phase: 'loading', view: null, scope });
  }

  useEffect(() => {
    const currentArgs = argsRef.current;
    const hasInstance = Boolean(currentArgs.instanceId) && currentArgs.idValues.length > 0 && Boolean(currentArgs.monitorObjectId);
    if (!hasInstance) {
      setState(blankState(scope));
      return undefined;
    }
    let active = true;
    const context = {
      monitorObjectId: String(currentArgs.monitorObjectId),
      instanceId: String(currentArgs.instanceId)
    };
    const loadInstant = async (query: string, unit: string): Promise<Probe> => {
      try {
        const result = await getInstanceInstantQuery(buildSearchParams(
          query,
          unit,
          currentArgs.idValues,
          currentArgs.instanceIdKeys,
          currentArgs.timeValues,
          undefined,
          false,
          currentArgs.intervalSec,
          context
        ));
        return { kind: 'ok', samples: readInstantSamples(result) };
      } catch {
        return { kind: 'error', samples: [] };
      }
    };
    const loadRange = async (query: string, unit: string): Promise<NamedSeries[]> => {
      try {
        const result = await getInstanceQuery(buildSearchParams(
          query,
          unit,
          currentArgs.idValues,
          currentArgs.instanceIdKeys,
          currentArgs.timeValues,
          undefined,
          false,
          currentArgs.intervalSec,
          context
        ));
        return readNamedSeries(result, 'container_name');
      } catch {
        return [];
      }
    };
    const instant = runWithConcurrency(INSTANT_JOBS, 4, async (job) => {
      const probe = await loadInstant(job.query, job.unit);
      return { key: job.key, probe };
    });
    const ranges = runWithConcurrency(RANGE_JOBS, 4, async (job) => {
      const series = await loadRange(job.query, job.unit);
      return { key: job.key, series };
    });
    Promise.all([instant, ranges]).then(([instantRows, rangeRows]) => {
      if (!active) return;
      const probeOf = (key: InstantKey): Probe => (
        instantRows.find((row) => row.key === key)?.probe ?? { kind: 'error', samples: [] }
      );
      const chartOf = (key: RangeKey): NamedSeries[] => (
        rangeRows.find((row) => row.key === key)?.series ?? []
      );
      setState({
        phase: 'ready',
        scope,
        view: buildDockerProView({
          hasInstance: true,
          freshSec: freshWindowSec(currentArgs.intervalSec),
          runningValue: probeOf('runningValue'),
          runningTime: probeOf('runningTime'),
          runningCapability: probeOf('runningCapability'),
          stoppedValue: probeOf('stoppedValue'),
          stoppedTime: probeOf('stoppedTime'),
          stoppedCapability: probeOf('stoppedCapability'),
          totalValue: probeOf('totalValue'),
          totalTime: probeOf('totalTime'),
          totalCapability: probeOf('totalCapability'),
          cpuValue: probeOf('cpuValue'),
          cpuTime: probeOf('cpuTime'),
          cpuCapability: probeOf('cpuCapability'),
          cpuChart: chartOf('cpuChart'),
          memPercentValue: probeOf('memPercentValue'),
          memPercentTime: probeOf('memPercentTime'),
          memPercentCapability: probeOf('memPercentCapability'),
          memPercentChart: chartOf('memPercentChart'),
          memBytesValue: probeOf('memBytesValue'),
          memBytesTime: probeOf('memBytesTime'),
          memBytesCapability: probeOf('memBytesCapability'),
          memBytesChart: chartOf('memBytesChart'),
          restartValue: probeOf('restartValue'),
          restartTime: probeOf('restartTime')
        })
      });
    });
    return () => {
      active = false;
    };
  }, [getInstanceInstantQuery, getInstanceQuery, scope]);

  return state.phase === 'ready' && state.view
    ? { phase: 'ready', view: state.view }
    : { phase: 'loading', view: null };
}
