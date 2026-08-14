export type CanvasRuntimeRefreshCause =
  | 'initial'
  | 'manual'
  | 'filter'
  | 'namespace'
  | 'periodic'
  | 'visibility';

export type CanvasSilentRefreshCause = Extract<
  CanvasRuntimeRefreshCause,
  'periodic' | 'visibility'
>;

export type CanvasIntervalChange =
  | 'unchanged'
  | 'start'
  | 'restart'
  | 'stop';

export const isSilentCanvasRuntimeRefresh = (
  cause: CanvasRuntimeRefreshCause,
): boolean => cause === 'periodic' || cause === 'visibility';

export const describeCanvasIntervalChange = (
  previousMs: number,
  nextMs: number,
): CanvasIntervalChange => {
  if (previousMs === nextMs) {
    return 'unchanged';
  }
  if (nextMs <= 0) {
    return 'stop';
  }
  if (previousMs <= 0) {
    return 'start';
  }
  return 'restart';
};

export const shouldRunCanvasIntervalTick = ({
  effectiveIntervalMs,
  documentHidden,
}: {
  effectiveIntervalMs: number;
  documentHidden: boolean;
}): boolean => effectiveIntervalMs > 0 && !documentHidden;

export const shouldSilentRefreshOnVisible = ({
  effectiveIntervalMs,
}: {
  effectiveIntervalMs: number;
}): boolean => effectiveIntervalMs > 0;

export const shouldSkipIntervalTick = (hasInflightRequest: boolean): boolean =>
  hasInflightRequest;

export type OwnerRequestGate =
  | { skip: true }
  | { skip: false; generation: number };

export const isStartedOwnerRequest = (
  gate: OwnerRequestGate,
): gate is { skip: false; generation: number } => !gate.skip;

export const beginOwnerRequest = ({
  silent,
  latestGeneration,
  inflightCount,
}: {
  silent: boolean;
  latestGeneration: number;
  inflightCount: number;
}): OwnerRequestGate => {
  if (silent && inflightCount > 0) {
    return { skip: true };
  }
  return { skip: false, generation: latestGeneration + 1 };
};

export const finishOwnerRequest = ({
  inflightCount,
}: {
  inflightCount: number;
}): { inflightCount: number } => ({
  inflightCount: Math.max(0, inflightCount - 1),
});

export const beginMappedOwnerRequest = (
  latest: Map<string, number>,
  inflight: Map<string, number>,
  ownerId: string,
  silent: boolean,
): OwnerRequestGate => {
  const inflightCount = inflight.get(ownerId) || 0;
  const gate = beginOwnerRequest({
    silent,
    latestGeneration: latest.get(ownerId) || 0,
    inflightCount,
  });
  if (!isStartedOwnerRequest(gate)) {
    return gate;
  }
  latest.set(ownerId, gate.generation);
  inflight.set(ownerId, inflightCount + 1);
  return gate;
};

export const finishMappedOwnerRequest = (
  _latest: Map<string, number>,
  inflight: Map<string, number>,
  ownerId: string,
  _generation: number,
): void => {
  const nextInflight = finishOwnerRequest({
    inflightCount: inflight.get(ownerId) || 0,
  }).inflightCount;
  if (nextInflight === 0) {
    inflight.delete(ownerId);
  } else {
    inflight.set(ownerId, nextInflight);
  }
};

export const shouldShowWidgetRuntimeLoading = (
  cause: CanvasRuntimeRefreshCause,
): boolean => !isSilentCanvasRuntimeRefresh(cause);

export const shouldKeepWidgetRuntimeDataOnError = ({
  cause,
  hasSuccessfulPayload,
}: {
  cause: CanvasRuntimeRefreshCause;
  hasSuccessfulPayload: boolean;
}): boolean => isSilentCanvasRuntimeRefresh(cause) && hasSuccessfulPayload;

export const resolveWidgetFetchCause = ({
  hasRequested,
  filterSearchChanged,
  namespaceSearchChanged,
  signatureChanged,
  reloadVersionChanged,
  tableQueryChanged,
  reloadCause,
}: {
  hasRequested: boolean;
  filterSearchChanged: boolean;
  namespaceSearchChanged: boolean;
  signatureChanged: boolean;
  reloadVersionChanged: boolean;
  tableQueryChanged: boolean;
  reloadCause: CanvasRuntimeRefreshCause;
}): CanvasRuntimeRefreshCause => {
  if (!hasRequested) {
    return 'initial';
  }
  if (filterSearchChanged) {
    return 'filter';
  }
  if (namespaceSearchChanged) {
    return 'namespace';
  }
  if (signatureChanged || tableQueryChanged) {
    return 'manual';
  }
  if (reloadVersionChanged) {
    return reloadCause;
  }
  return reloadCause;
};

