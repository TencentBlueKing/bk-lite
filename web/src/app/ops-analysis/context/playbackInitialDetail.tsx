'use client';

import { createContext, useContext } from 'react';
import type { CanvasType } from '@/app/ops-analysis/constants/canvasTypes';
import {
  fetchSharedCanvasDetail,
  rememberCanvasDetailIfAbsent,
} from '@/app/ops-analysis/utils/canvasDetailCache';

export interface PlaybackInitialDetail {
  resourceType: CanvasType;
  canvasId: number;
  detail: unknown;
}

const PlaybackInitialDetailContext = createContext<PlaybackInitialDetail | null>(null);

export const PlaybackInitialDetailProvider = PlaybackInitialDetailContext.Provider;

export const usePlaybackInitialDetail = () => useContext(PlaybackInitialDetailContext);

export const readPlaybackInitialDetail = <T,>(
  seeded: PlaybackInitialDetail | null,
  resourceType: CanvasType,
  id: string | number,
): T | undefined => {
  if (!seeded || seeded.resourceType !== resourceType || String(seeded.canvasId) !== String(id)) {
    return undefined;
  }
  return seeded.detail as T;
};

const abortError = (): Error => {
  const error = new Error('The operation was aborted');
  error.name = 'AbortError';
  return error;
};

/**
 * 播放态优先用切入确认拿到的详情；没有注入时才请求。刷新周期不走这条详情请求。
 * fetchDetail 必须使用共享飞行的 signal。callerSignal 只解除这一位使用者，
 * 最后一位离开才 abort 物理请求。
 */
export const loadPlaybackCanvasDetail = async <T,>(
  seeded: PlaybackInitialDetail | null,
  resourceType: CanvasType,
  id: string | number,
  fetchDetail: (signal: AbortSignal) => Promise<T>,
  callerSignal?: AbortSignal,
): Promise<T> => {
  const initial = readPlaybackInitialDetail<T>(seeded, resourceType, id);
  const canvasId = Number(id);
  if (initial !== undefined) {
    if (Number.isFinite(canvasId)) {
      rememberCanvasDetailIfAbsent(resourceType, canvasId, initial);
    }
    return initial;
  }
  if (callerSignal?.aborted) {
    throw abortError();
  }
  if (!Number.isFinite(canvasId)) {
    return fetchDetail(callerSignal ?? new AbortController().signal);
  }
  return fetchSharedCanvasDetail(
    resourceType,
    canvasId,
    (signal) => fetchDetail(signal),
    callerSignal,
  ) as Promise<T>;
};
