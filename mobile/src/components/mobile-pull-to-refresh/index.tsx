'use client';

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react';
import { PullToRefresh, Toast } from 'antd-mobile';
import { useTranslation } from '@/utils/i18n';
import {
  getDesktopPullIntent,
  getDesktopPullProgress,
  type DesktopPullIntent,
} from './desktop-pull';
import styles from './index.module.css';

type PullStatus = 'pulling' | 'canRelease' | 'refreshing' | 'complete';
type DesktopPullStatus = PullStatus | 'idle';

interface DesktopPullState {
  failed: boolean;
  headOffset: number;
  status: DesktopPullStatus;
}

interface MouseGesture {
  claimed: boolean;
  pointerId: number;
  startX: number;
  startY: number;
}

interface MobilePullToRefreshProps {
  children: ReactNode;
  disabled?: boolean;
  onRefresh: () => Promise<unknown>;
}

const EMPTY_DESKTOP_PULL: DesktopPullState = { failed: false, headOffset: 0, status: 'idle' };

function isAtScrollStart(target: EventTarget | null) {
  if (!(target instanceof Element)) return false;

  let current: Element | null = target;
  while (current) {
    const style = window.getComputedStyle(current);
    const scrollable = /(auto|scroll|overlay)/.test(style.overflowY)
      && current.scrollHeight > current.clientHeight;
    if (scrollable && current.scrollTop > 0) return false;
    current = current.parentElement;
  }

  return window.scrollY <= 0 && (document.scrollingElement?.scrollTop || 0) <= 0;
}

export default function MobilePullToRefresh({
  children,
  disabled = false,
  onRefresh,
}: MobilePullToRefreshProps) {
  const { t } = useTranslation();
  const [refreshFailed, setRefreshFailed] = useState(false);
  const [desktopPull, setDesktopPull] = useState<DesktopPullState>(EMPTY_DESKTOP_PULL);
  const rootRef = useRef<HTMLDivElement>(null);
  const gestureRef = useRef<MouseGesture | null>(null);
  const refreshPromiseRef = useRef<Promise<boolean> | null>(null);
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const suppressClickRef = useRef(false);

  const statusText: Record<PullStatus, string> = {
    pulling: t('refresh.pulling'),
    canRelease: t('refresh.canRelease'),
    refreshing: t('refresh.refreshing'),
    complete: t('refresh.complete'),
  };

  const handleRefresh = useCallback(() => {
    if (refreshPromiseRef.current) return refreshPromiseRef.current;

    setRefreshFailed(false);
    const refreshPromise = (async () => {
      try {
        await onRefresh();
        return true;
      } catch {
        setRefreshFailed(true);
        Toast.show({ content: t('refresh.failed'), icon: 'fail' });
        return false;
      } finally {
        refreshPromiseRef.current = null;
      }
    })();
    refreshPromiseRef.current = refreshPromise;
    return refreshPromise;
  }, [onRefresh, t]);

  const clearSettleTimer = useCallback(() => {
    if (!settleTimerRef.current) return;
    clearTimeout(settleTimerRef.current);
    settleTimerRef.current = null;
  }, []);

  const resetGesture = useCallback((event?: ReactPointerEvent<HTMLDivElement>) => {
    const gesture = gestureRef.current;
    if (gesture?.claimed && event?.currentTarget.hasPointerCapture(gesture.pointerId)) {
      event.currentTarget.releasePointerCapture(gesture.pointerId);
    }
    gestureRef.current = null;
  }, []);

  const finishDesktopRefresh = useCallback(async () => {
    setDesktopPull({ failed: false, headOffset: 40, status: 'refreshing' });
    const succeeded = await handleRefresh();
    setDesktopPull({ failed: !succeeded, headOffset: 40, status: 'complete' });
    clearSettleTimer();
    settleTimerRef.current = setTimeout(() => {
      settleTimerRef.current = null;
      setDesktopPull(EMPTY_DESKTOP_PULL);
    }, 500);
  }, [clearSettleTimer, handleRefresh]);

  const handlePointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (disabled || refreshPromiseRef.current || event.pointerType !== 'mouse' || event.button !== 0) return;
    if (!(event.target instanceof Element)) return;
    if (event.target.closest('input, textarea, select, [contenteditable="true"]')) return;
    if (!isAtScrollStart(event.target)) return;

    clearSettleTimer();
    setDesktopPull(EMPTY_DESKTOP_PULL);
    gestureRef.current = {
      claimed: false,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
    };
  }, [clearSettleTimer, disabled]);

  const updateDesktopPull = useCallback((
    event: ReactPointerEvent<HTMLDivElement>,
    gesture: MouseGesture,
    intent: DesktopPullIntent,
  ) => {
    if (intent !== 'pulling') return;
    if (!gesture.claimed) {
      gesture.claimed = true;
      event.currentTarget.setPointerCapture(gesture.pointerId);
    }
    if (event.cancelable) event.preventDefault();
    event.stopPropagation();
    const progress = getDesktopPullProgress(event.clientY - gesture.startY);
    setDesktopPull({
      failed: false,
      headOffset: progress.headOffset,
      status: progress.canRelease ? 'canRelease' : 'pulling',
    });
  }, []);

  const handlePointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const gesture = gestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    if (disabled || !isAtScrollStart(event.target)) {
      resetGesture(event);
      setDesktopPull(EMPTY_DESKTOP_PULL);
      return;
    }

    const intent = getDesktopPullIntent(
      event.clientX - gesture.startX,
      event.clientY - gesture.startY,
    );
    if (intent === 'cancelled') {
      resetGesture(event);
      setDesktopPull(EMPTY_DESKTOP_PULL);
      return;
    }
    updateDesktopPull(event, gesture, intent);
  }, [disabled, resetGesture, updateDesktopPull]);

  const handlePointerUp = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const gesture = gestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;

    const intent = getDesktopPullIntent(
      event.clientX - gesture.startX,
      event.clientY - gesture.startY,
    );
    const progress = getDesktopPullProgress(event.clientY - gesture.startY);
    const claimed = gesture.claimed || intent === 'pulling';
    if (claimed) {
      if (event.cancelable) event.preventDefault();
      event.stopPropagation();
      suppressClickRef.current = true;
      setTimeout(() => { suppressClickRef.current = false; }, 0);
    }
    resetGesture(event);

    if (claimed && progress.canRelease && !disabled && !refreshPromiseRef.current) {
      void finishDesktopRefresh();
    } else {
      setDesktopPull(EMPTY_DESKTOP_PULL);
    }
  }, [disabled, finishDesktopRefresh, resetGesture]);

  const handlePointerCancel = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    resetGesture(event);
    setDesktopPull(EMPTY_DESKTOP_PULL);
  }, [resetGesture]);

  useEffect(() => () => clearSettleTimer(), [clearSettleTimer]);

  useEffect(() => {
    if (!disabled || !gestureRef.current) return;
    const gesture = gestureRef.current;
    if (gesture.claimed && rootRef.current?.hasPointerCapture(gesture.pointerId)) {
      rootRef.current.releasePointerCapture(gesture.pointerId);
    }
    gestureRef.current = null;
    setDesktopPull(EMPTY_DESKTOP_PULL);
  }, [disabled]);

  const desktopStatusText = desktopPull.status === 'idle'
    ? ''
    : desktopPull.status === 'complete' && desktopPull.failed
      ? t('refresh.failed')
      : statusText[desktopPull.status];
  const rootStyle = {
    '--desktop-pull-offset': `${desktopPull.headOffset}px`,
    '--desktop-pull-opacity': Math.min(1, desktopPull.headOffset / 20),
  } as CSSProperties;

  return (
    <div
      ref={rootRef}
      className={styles.root}
      data-mouse-dragging={desktopPull.status === 'pulling' || desktopPull.status === 'canRelease'}
      style={rootStyle}
      onClickCapture={(event) => {
        if (!suppressClickRef.current) return;
        event.preventDefault();
        event.stopPropagation();
      }}
      onPointerCancel={handlePointerCancel}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
    >
      <div className={styles.desktopPullHead} aria-live="polite">
        {desktopStatusText}
      </div>
      <div className={styles.pullSurface}>
        <PullToRefresh
          disabled={disabled}
          onRefresh={handleRefresh}
          renderText={(status) => (
            status === 'complete' && refreshFailed ? t('refresh.failed') : statusText[status]
          )}
        >
          {children}
        </PullToRefresh>
      </div>
    </div>
  );
}
