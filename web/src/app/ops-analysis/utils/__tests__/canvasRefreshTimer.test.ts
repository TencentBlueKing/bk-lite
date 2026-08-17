import { describe, expect, it } from 'vitest';
import {
  beginMappedOwnerRequest,
  beginOwnerRequest,
  describeCanvasIntervalChange,
  finishMappedOwnerRequest,
  finishOwnerRequest,
  isStartedOwnerRequest,
  resolveWidgetFetchCause,
  shouldKeepWidgetRuntimeDataOnError,
  shouldRunCanvasIntervalTick,
  shouldShowWidgetRuntimeLoading,
  shouldSilentRefreshOnVisible,
  shouldSkipIntervalTick,
} from '@/app/ops-analysis/utils/canvasRefreshTimer';

describe('canvas refresh timer cadence', () => {
  it('starts from now when turning on, without an extra immediate request', () => {
    expect(describeCanvasIntervalChange(0, 60000)).toBe('start');
  });

  it('restarts from now when switching non-zero intervals', () => {
    expect(describeCanvasIntervalChange(60000, 300000)).toBe('restart');
  });

  it('stops later ticks when turning off', () => {
    expect(describeCanvasIntervalChange(60000, 0)).toBe('stop');
  });

  it('does not refresh on visible when the interval is off', () => {
    expect(shouldSilentRefreshOnVisible({ effectiveIntervalMs: 0 })).toBe(false);
    expect(
      shouldRunCanvasIntervalTick({
        effectiveIntervalMs: 0,
        documentHidden: false,
      }),
    ).toBe(false);
  });

  it('pauses ticks while hidden and allows a silent refresh when visible', () => {
    expect(
      shouldRunCanvasIntervalTick({
        effectiveIntervalMs: 60000,
        documentHidden: true,
      }),
    ).toBe(false);
    expect(shouldSilentRefreshOnVisible({ effectiveIntervalMs: 60000 })).toBe(
      true,
    );
  });

  it('skips an interval tick when the same owner still has any request in flight', () => {
    expect(shouldSkipIntervalTick(true)).toBe(true);
    expect(shouldSkipIntervalTick(false)).toBe(false);
  });
});

describe('owner request generation', () => {
  it('skips a silent refresh while any request is in flight and keeps the current generation', () => {
    expect(
      beginOwnerRequest({
        silent: true,
        latestGeneration: 1,
        inflightCount: 1,
      }),
    ).toEqual({ skip: true });
  });

  it('does not skip a user request while a silent request is in flight', () => {
    expect(
      beginOwnerRequest({
        silent: false,
        latestGeneration: 1,
        inflightCount: 1,
      }),
    ).toEqual({ skip: false, generation: 2 });
  });

  it('decrements inflight count when a stale request finishes so remaining requests still block silent ticks', () => {
    expect(
      finishOwnerRequest({
        inflightCount: 2,
      }),
    ).toEqual({ inflightCount: 1 });
    expect(
      beginOwnerRequest({
        silent: true,
        latestGeneration: 2,
        inflightCount: 1,
      }),
    ).toEqual({ skip: true });
    expect(
      finishOwnerRequest({
        inflightCount: 1,
      }),
    ).toEqual({ inflightCount: 0 });
  });

  it('skips a later silent tick after the latest request finishes while an older request is still in flight', () => {
    let latestGeneration = 0;
    let inflightCount = 0;

    const silentA = beginOwnerRequest({
      silent: true,
      latestGeneration,
      inflightCount,
    });
    expect(silentA.skip).toBe(false);
    if (isStartedOwnerRequest(silentA)) {
      latestGeneration = silentA.generation;
      inflightCount += 1;
    }

    const manualB = beginOwnerRequest({
      silent: false,
      latestGeneration,
      inflightCount,
    });
    expect(manualB.skip).toBe(false);
    if (isStartedOwnerRequest(manualB)) {
      latestGeneration = manualB.generation;
      inflightCount += 1;
    }

    inflightCount = finishOwnerRequest({ inflightCount }).inflightCount;
    expect(inflightCount).toBe(1);

    expect(
      beginOwnerRequest({
        silent: true,
        latestGeneration,
        inflightCount,
      }),
    ).toEqual({ skip: true });
  });

  it('skips a visibility tick after a newer manual finishes while an older manual is still in flight', () => {
    let latestGeneration = 0;
    let inflightCount = 0;

    const manualA = beginOwnerRequest({
      silent: false,
      latestGeneration,
      inflightCount,
    });
    if (isStartedOwnerRequest(manualA)) {
      latestGeneration = manualA.generation;
      inflightCount += 1;
    }

    const manualB = beginOwnerRequest({
      silent: false,
      latestGeneration,
      inflightCount,
    });
    if (isStartedOwnerRequest(manualB)) {
      latestGeneration = manualB.generation;
      inflightCount += 1;
    }

    inflightCount = finishOwnerRequest({ inflightCount }).inflightCount;

    expect(
      beginOwnerRequest({
        silent: true,
        latestGeneration,
        inflightCount,
      }),
    ).toEqual({ skip: true });
  });

  it('tracks per-owner inflight so one busy node does not lock another', () => {
    const latest = new Map<string, number>();
    const inflight = new Map<string, number>();

    const first = beginMappedOwnerRequest(latest, inflight, 'a', false);
    const second = beginMappedOwnerRequest(latest, inflight, 'b', true);

    expect(first).toEqual({ skip: false, generation: 1 });
    expect(second).toEqual({ skip: false, generation: 1 });

    const skipped = beginMappedOwnerRequest(latest, inflight, 'a', true);
    expect(skipped).toEqual({ skip: true });

    if (isStartedOwnerRequest(first)) {
      finishMappedOwnerRequest(latest, inflight, 'a', first.generation);
    }
    expect(beginMappedOwnerRequest(latest, inflight, 'a', true)).toEqual({
      skip: false,
      generation: 2,
    });
  });
});

describe('widget runtime loading by refresh cause', () => {
  it('shows loading for first load, manual refresh, and filter or namespace changes', () => {
    expect(shouldShowWidgetRuntimeLoading('initial')).toBe(true);
    expect(shouldShowWidgetRuntimeLoading('manual')).toBe(true);
    expect(shouldShowWidgetRuntimeLoading('filter')).toBe(true);
    expect(shouldShowWidgetRuntimeLoading('namespace')).toBe(true);
  });

  it('does not show loading for periodic or visibility refresh', () => {
    expect(shouldShowWidgetRuntimeLoading('periodic')).toBe(false);
    expect(shouldShowWidgetRuntimeLoading('visibility')).toBe(false);
  });

  it('keeps previous successful data when a silent refresh fails', () => {
    expect(
      shouldKeepWidgetRuntimeDataOnError({
        cause: 'periodic',
        hasSuccessfulPayload: true,
      }),
    ).toBe(true);
    expect(
      shouldKeepWidgetRuntimeDataOnError({
        cause: 'manual',
        hasSuccessfulPayload: true,
      }),
    ).toBe(false);
    expect(
      shouldKeepWidgetRuntimeDataOnError({
        cause: 'periodic',
        hasSuccessfulPayload: false,
      }),
    ).toBe(false);
  });
});

describe('resolveWidgetFetchCause', () => {
  it('treats filter and namespace changes as loading refreshes even if the last toolbar cause was periodic', () => {
    expect(
      resolveWidgetFetchCause({
        hasRequested: true,
        filterSearchChanged: true,
        namespaceSearchChanged: false,
        signatureChanged: false,
        reloadVersionChanged: true,
        tableQueryChanged: false,
        reloadCause: 'periodic',
      }),
    ).toBe('filter');
  });

  it('uses the reload cause when only the reload version changed', () => {
    expect(
      resolveWidgetFetchCause({
        hasRequested: true,
        filterSearchChanged: false,
        namespaceSearchChanged: false,
        signatureChanged: false,
        reloadVersionChanged: true,
        tableQueryChanged: false,
        reloadCause: 'periodic',
      }),
    ).toBe('periodic');
  });
});
