'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { CanvasType } from '@/app/ops-analysis/constants/canvasTypes';
import { createCarouselRemainingClock } from '@/app/ops-analysis/utils/carouselRemainingClock';
import {
  createCarouselPlayerState,
  isCarouselBusinessFailure,
  isCarouselSessionFailure,
  reduceCarouselLoad,
  reduceCarouselPlayer,
  type CarouselPlayerAction,
  type CarouselPlayerState,
  type CarouselSlideInput,
} from '@/app/ops-analysis/utils/carouselPlayer';

export const CAROUSEL_PLAYBACK_TICK_MS = 250;
export const CAROUSEL_PREFETCH_LEAD_MS = 2000;

export interface CarouselPlaybackSlide {
  key: string;
  available: boolean;
  dwellSeconds: number;
  resourceType: CanvasType;
  canvasId: number;
}

export type CarouselEnterOutcome =
  | { status: 'ok'; detail: unknown }
  | { status: 'skip' }
  | { status: 'ignore' };

const toInput = (slide: CarouselPlaybackSlide): CarouselSlideInput => ({
  key: slide.key,
  available: slide.available,
  dwellSeconds: slide.dwellSeconds,
});

const isAborted = (error: unknown, signal: AbortSignal): boolean => {
  if (signal.aborted) {
    return true;
  }
  if (typeof error !== 'object' || error === null) {
    return false;
  }
  const name = 'name' in error ? String((error as { name?: unknown }).name) : '';
  const code = 'code' in error ? String((error as { code?: unknown }).code) : '';
  return name === 'AbortError' || name === 'CanceledError' || code === 'ERR_CANCELED';
};

const oneAttempt = async (
  loadDetail: (slide: CarouselPlaybackSlide, signal: AbortSignal) => Promise<unknown>,
  slide: CarouselPlaybackSlide,
  signal: AbortSignal,
): Promise<CarouselEnterOutcome | { status: 'retry' }> => {
  try {
    return { status: 'ok', detail: await loadDetail(slide, signal) };
  } catch (error) {
    if (isAborted(error, signal) || isCarouselSessionFailure(error)) {
      return { status: 'ignore' };
    }
    if (isCarouselBusinessFailure(error)) {
      return { status: 'skip' };
    }
    return { status: 'retry' };
  }
};

/** 切入确认：403/404 立即跳过，瞬时错误再试一次，401 与取消都不记失败。 */
export const confirmCarouselEnter = async (
  loadDetail: (slide: CarouselPlaybackSlide, signal: AbortSignal) => Promise<unknown>,
  slide: CarouselPlaybackSlide,
  signal: AbortSignal,
): Promise<CarouselEnterOutcome> => {
  const first = await oneAttempt(loadDetail, slide, signal);
  if (first.status !== 'retry') {
    return first;
  }
  const second = await oneAttempt(loadDetail, slide, signal);
  return second.status === 'retry' ? { status: 'skip' } : second;
};

/** 当前项的 key 或可用性变了、或播放列表被整表重载时，才重新确认。重排和停留秒数只改计时。 */
export const carouselPlaybackNeedsReset = (
  previous: { resetKey: string; key?: string; available?: boolean },
  next: { resetKey: string; slides: readonly { key: string; available: boolean }[] },
): boolean => {
  if (previous.resetKey !== next.resetKey || !previous.key) {
    return true;
  }
  const slide = next.slides.find((item) => item.key === previous.key);
  if (!slide) {
    return true;
  }
  return slide.available !== previous.available;
};

const nextSlide = (
  slides: readonly CarouselPlaybackSlide[],
  player: CarouselPlayerState,
): CarouselPlaybackSlide | undefined => {
  const upcoming = player.slides.findIndex((slide, index) => (
    slide.available && index !== player.index && index > player.index
  ));
  const fallback = player.slides.findIndex((slide, index) => slide.available && index !== player.index);
  const target = upcoming >= 0 ? upcoming : fallback;
  if (target < 0) {
    return undefined;
  }
  const key = player.slides[target]?.key;
  return slides.find((slide) => slide.key === key);
};

export const useCarouselPlaybackSession = ({
  slides,
  enabled,
  loadDetail,
  resetKey = '',
  startPaused = false,
  confirmWhilePaused = false,
  retainUnavailable = false,
}: {
  slides: readonly CarouselPlaybackSlide[];
  enabled: boolean;
  loadDetail: (slide: CarouselPlaybackSlide, signal: AbortSignal) => Promise<unknown>;
  /** 播放列表重新拉取（切换轮播或组织）时递增，强制重新确认当前画布。 */
  resetKey?: string;
  /** 预览默认暂停。缺省为进入即播放。 */
  startPaused?: boolean;
  /** 暂停时也确认当前画布。缺省时暂停会取消确认。 */
  confirmWhilePaused?: boolean;
  /** 刷新列表时，当前项即使失效也留在原位。 */
  retainUnavailable?: boolean;
}) => {
  const slidesRef = useRef(slides);
  slidesRef.current = slides;
  const loadRef = useRef(loadDetail);
  loadRef.current = loadDetail;
  const playlistSignature = `${resetKey}|${slides.map((slide) => `${slide.key}:${Number(slide.available)}:${slide.dwellSeconds}`).join('|')}`;
  const signatureRef = useRef<string | null>(null);
  const resetKeyRef = useRef<string | null>(null);
  const [player, setPlayer] = useState<CarouselPlayerState>(() => {
    const created = createCarouselPlayerState(slides.map(toInput));
    return startPaused ? { ...created, paused: true } : created;
  });
  const [confirming, setConfirming] = useState(false);
  const [armedVisit, setArmedVisit] = useState<number | null>(null);
  const [initialDetail, setInitialDetail] = useState<unknown>(undefined);
  const [prefetchLead, setPrefetchLead] = useState(false);
  const confirmingRef = useRef(false);
  const armedVisitRef = useRef<number | null>(null);
  const prefetchDone = useRef<string | null>(null);
  const prefetchLeadRef = useRef(false);
  const playerRef = useRef(player);
  const remainingRef = useRef(player.remainingMs);
  const holdRef = useRef(player.holdMs);
  const clockRef = useRef<ReturnType<typeof createCarouselRemainingClock> | null>(null);
  if (clockRef.current === null) {
    clockRef.current = createCarouselRemainingClock(player.remainingMs);
  }
  const clock = clockRef.current;
  playerRef.current = player;

  const readLive = (): CarouselPlayerState => {
    const current = playerRef.current;
    if (current.remainingMs === remainingRef.current && current.holdMs === holdRef.current) {
      return current;
    }
    return {
      ...current,
      remainingMs: remainingRef.current,
      holdMs: holdRef.current,
    };
  };

  const syncPrefetchLead = () => {
    const state = playerRef.current;
    const due = state.index >= 0
      && !state.paused
      && holdRef.current <= 0
      && armedVisitRef.current === state.visit
      && remainingRef.current <= CAROUSEL_PREFETCH_LEAD_MS;
    if (due === prefetchLeadRef.current) {
      return;
    }
    prefetchLeadRef.current = due;
    setPrefetchLead(due);
  };

  const publish = (next: CarouselPlayerState) => {
    playerRef.current = next;
    remainingRef.current = next.remainingMs;
    holdRef.current = next.holdMs;
    clock.set(next.remainingMs);
    return next;
  };

  const commit = (next: CarouselPlayerState) => {
    publish(next);
    setPlayer(next);
    syncPrefetchLead();
  };

  const runtimeRef = useRef({ readLive, commit, syncPrefetchLead });
  runtimeRef.current = { readLive, commit, syncPrefetchLead };

  const disarm = () => {
    armedVisitRef.current = null;
    setArmedVisit(null);
    setInitialDetail(undefined);
  };

  useEffect(() => {
    if (signatureRef.current === playlistSignature) {
      return;
    }
    const isFirst = signatureRef.current === null;
    signatureRef.current = playlistSignature;
    if (isFirst) {
      resetKeyRef.current = resetKey;
      return;
    }
    const previous = playerRef.current;
    const previousSlide = previous.index >= 0 ? previous.slides[previous.index] : undefined;
    const nextSlides = slidesRef.current;
    const needsReset = carouselPlaybackNeedsReset(
      {
        resetKey: resetKeyRef.current ?? '',
        key: previousSlide?.key,
        available: previousSlide?.available,
      },
      { resetKey, slides: nextSlides },
    );
    resetKeyRef.current = resetKey;
    if (!needsReset) {
      const base = runtimeRef.current.readLive();
      const next = reduceCarouselPlayer(base, {
        type: 'syncSlides',
        slides: nextSlides.map(toInput),
      });
      if (next !== base) {
        runtimeRef.current.commit(next);
      }
      return;
    }
    disarm();
    confirmingRef.current = false;
    setConfirming(false);
    const base = runtimeRef.current.readLive();
    runtimeRef.current.commit(reduceCarouselPlayer(base, {
      type: 'reset',
      slides: nextSlides.map(toInput),
      preferKey: base.slides[base.index]?.key ?? null,
      retainUnavailable,
    }));
  }, [playlistSignature, resetKey, retainUnavailable]);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      const current = runtimeRef.current.readLive();
      if (current.paused || confirmingRef.current) {
        return;
      }
      if (current.index >= 0 && armedVisitRef.current !== current.visit) {
        return;
      }
      const next = reduceCarouselPlayer(current, { type: 'tick', deltaMs: CAROUSEL_PLAYBACK_TICK_MS });
      if (next === current) {
        return;
      }
      const sameSlide = next.index === current.index
        && next.visit === current.visit
        && next.paused === current.paused
        && next.slides === current.slides;
      const keepOffReact = (holdMs: number) => {
        remainingRef.current = next.remainingMs;
        holdRef.current = holdMs;
        clock.set(next.remainingMs);
      };
      if (sameSlide && next.holdMs === current.holdMs) {
        keepOffReact(current.holdMs);
        runtimeRef.current.syncPrefetchLead();
        return;
      }
      if (sameSlide && next.holdMs > 0) {
        keepOffReact(next.holdMs);
        return;
      }
      runtimeRef.current.commit(next);
    }, CAROUSEL_PLAYBACK_TICK_MS);
    return () => window.clearInterval(timer);
  }, [enabled]);

  const current = player.index >= 0 ? player.slides[player.index] : undefined;
  useEffect(() => {
    if (!enabled || !current?.available || player.holdMs > 0) {
      return undefined;
    }
    if ((!confirmWhilePaused && player.paused) || armedVisitRef.current === player.visit) {
      return undefined;
    }
    const slide = slidesRef.current.find((item) => item.key === current.key);
    if (!slide) {
      return undefined;
    }
    const visit = player.visit;
    const controller = new AbortController();
    let active = true;
    confirmingRef.current = true;
    setConfirming(true);
    setInitialDetail(undefined);
    void confirmCarouselEnter(
      (target, signal) => loadRef.current(target, signal),
      slide,
      controller.signal,
    ).then((result) => {
      if (!active) {
        return;
      }
      confirmingRef.current = false;
      setConfirming(false);
      if (result.status === 'ok') {
        armedVisitRef.current = visit;
        setArmedVisit(visit);
        setInitialDetail(result.detail);
        return;
      }
      if (result.status === 'skip') {
        runtimeRef.current.commit(reduceCarouselLoad(runtimeRef.current.readLive(), {
          key: slide.key,
          phase: 'enter',
          ok: false,
          business: true,
        }));
      }
    });
    return () => {
      active = false;
      controller.abort();
      confirmingRef.current = false;
      setConfirming(false);
    };
  }, [
    confirmWhilePaused,
    current?.available,
    current?.key,
    enabled,
    player.holdMs,
    confirmWhilePaused ? false : player.paused,
    player.visit,
  ]);

  useEffect(() => {
    if (!prefetchLead || player.index < 0) {
      return undefined;
    }
    const slide = nextSlide(slidesRef.current, playerRef.current);
    if (!slide) {
      return undefined;
    }
    const mark = `${player.visit}:${slide.key}`;
    const done = prefetchDone.current;
    if (done === mark) {
      return undefined;
    }
    const controller = new AbortController();
    let settled = false;
    void loadRef.current(slide, controller.signal).then(() => {
      settled = true;
      if (!controller.signal.aborted) {
        prefetchDone.current = mark;
      }
    }).catch((error) => {
      if (controller.signal.aborted || isAborted(error, controller.signal)) {
        return;
      }
      settled = true;
      prefetchDone.current = mark;
      if (isCarouselBusinessFailure(error)) {
        runtimeRef.current.commit(reduceCarouselLoad(runtimeRef.current.readLive(), {
          key: slide.key,
          phase: 'prefetch',
          ok: false,
          business: true,
        }));
      }
    });
    return () => {
      controller.abort();
      if (!settled) {
        prefetchDone.current = null;
      }
    };
  }, [player.index, player.visit, prefetchLead]);

  const dispatch = useCallback((action: Exclude<CarouselPlayerAction, { type: 'tick' } | { type: 'reset' }>) => {
    const base = runtimeRef.current.readLive();
    const next = reduceCarouselPlayer(base, action);
    if (next === base) {
      return;
    }
    runtimeRef.current.commit(next);
  }, []);

  const ready = !confirming && player.index >= 0 && armedVisit === player.visit;

  return {
    player,
    confirming,
    ready,
    dispatch,
    initialDetail: ready ? initialDetail : undefined,
    remainingClock: clock,
  };
};
