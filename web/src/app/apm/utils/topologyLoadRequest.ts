import type { ApmTopologyGraph } from '@/app/apm/types';
import type { LatestRequestGuard } from '@/context/latestRequestGuard';

export interface TopologyTimeRange {
  startedAt: string;
  endedAt: string;
}

export interface TopologyLoadSuccessPayload {
  graph: ApmTopologyGraph;
  range: TopologyTimeRange;
}

export interface TopologyLoadView {
  graph: ApmTopologyGraph;
  range: TopologyTimeRange;
  state: 'ready' | 'empty';
}

export function beginTopologyLoad(guard: LatestRequestGuard): number {
  return guard.begin();
}

export function commitTopologyLoadSuccess(
  guard: LatestRequestGuard,
  requestId: number,
  payload: TopologyLoadSuccessPayload,
  apply: (next: TopologyLoadView) => void,
): boolean {
  return guard.commitIfCurrent(requestId, () => {
    apply({
      graph: payload.graph,
      range: payload.range,
      state: payload.graph.nodes.length ? 'ready' : 'empty',
    });
  });
}

export function commitTopologyLoadFailure(
  guard: LatestRequestGuard,
  requestId: number,
  reportError: () => void,
): boolean {
  return guard.commitIfCurrent(requestId, reportError);
}
