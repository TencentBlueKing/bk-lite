import { useCallback, useEffect, useRef, useState } from 'react';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  normalizeCanvasRefreshInterval,
  type CanvasRefreshIntervalMs,
} from '@/app/ops-analysis/utils/canvasRefreshInterval';
import {
  shouldRunCanvasIntervalTick,
  shouldSilentRefreshOnVisible,
  type CanvasSilentRefreshCause,
} from '@/app/ops-analysis/utils/canvasRefreshTimer';

interface UseCanvasPeriodicRefreshParams {
  canvasId?: string | number;
  savedInterval: unknown;
  canPersist: boolean;
  enabled?: boolean;
  patchRefreshInterval?: (interval: CanvasRefreshIntervalMs) => Promise<void>;
  onPeriodicRefresh: (cause: CanvasSilentRefreshCause) => void;
  onSavedIntervalChange?: (interval: CanvasRefreshIntervalMs) => void;
}

export const useCanvasPeriodicRefresh = ({
  canvasId,
  savedInterval,
  canPersist,
  enabled = true,
  patchRefreshInterval,
  onPeriodicRefresh,
  onSavedIntervalChange,
}: UseCanvasPeriodicRefreshParams) => {
  const { t } = useTranslation();
  const normalizedSaved = normalizeCanvasRefreshInterval(savedInterval);
  const [effectiveRefreshInterval, setEffectiveRefreshInterval] =
    useState<CanvasRefreshIntervalMs>(normalizedSaved);
  const [timerEpoch, setTimerEpoch] = useState(0);
  const effectiveRef = useRef(effectiveRefreshInterval);
  const onPeriodicRefreshRef = useRef(onPeriodicRefresh);
  const persistRequestIdRef = useRef(0);
  const lastCanvasIdRef = useRef(canvasId);
  const sessionOverrideRef = useRef(false);

  useEffect(() => {
    onPeriodicRefreshRef.current = onPeriodicRefresh;
  }, [onPeriodicRefresh]);

  useEffect(() => {
    const next = normalizeCanvasRefreshInterval(savedInterval);
    const canvasChanged = canvasId !== lastCanvasIdRef.current;
    lastCanvasIdRef.current = canvasId;
    if (canvasChanged) {
      sessionOverrideRef.current = false;
      setEffectiveRefreshInterval(next);
      effectiveRef.current = next;
      return;
    }
    if (sessionOverrideRef.current) {
      return;
    }
    setEffectiveRefreshInterval(next);
    effectiveRef.current = next;
  }, [canvasId, savedInterval]);

  useEffect(() => {
    effectiveRef.current = effectiveRefreshInterval;
  }, [effectiveRefreshInterval]);

  useEffect(() => {
    if (!enabled || effectiveRefreshInterval <= 0) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      if (
        !shouldRunCanvasIntervalTick({
          effectiveIntervalMs: effectiveRefreshInterval,
          documentHidden: typeof document !== 'undefined' && document.hidden,
        })
      ) {
        return;
      }
      onPeriodicRefreshRef.current('periodic');
    }, effectiveRefreshInterval);
    return () => window.clearInterval(timer);
  }, [canvasId, effectiveRefreshInterval, enabled, timerEpoch]);

  useEffect(() => {
    if (typeof document === 'undefined' || !enabled) {
      return undefined;
    }
    const handleVisibility = () => {
      if (document.hidden) {
        return;
      }
      if (
        !shouldSilentRefreshOnVisible({
          effectiveIntervalMs: effectiveRef.current,
        })
      ) {
        return;
      }
      onPeriodicRefreshRef.current('visibility');
      setTimerEpoch((current) => current + 1);
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [canvasId, enabled]);

  const handleFrequencyChange = useCallback(
    (nextInterval: number) => {
      const next = normalizeCanvasRefreshInterval(nextInterval);
      const previous = effectiveRef.current;
      sessionOverrideRef.current = true;
      setEffectiveRefreshInterval(next);
      effectiveRef.current = next;
      if (!canPersist || !patchRefreshInterval) {
        return;
      }
      const requestId = ++persistRequestIdRef.current;
      void patchRefreshInterval(next)
        .then(() => {
          if (requestId !== persistRequestIdRef.current) {
            return;
          }
          onSavedIntervalChange?.(next);
        })
        .catch(() => {
          if (requestId !== persistRequestIdRef.current) {
            return;
          }
          sessionOverrideRef.current = false;
          setEffectiveRefreshInterval(previous);
          effectiveRef.current = previous;
          message.error(t('common.saveFailed'));
        });
    },
    [canPersist, onSavedIntervalChange, patchRefreshInterval, t],
  );

  return {
    effectiveRefreshInterval,
    handleFrequencyChange,
  };
};
