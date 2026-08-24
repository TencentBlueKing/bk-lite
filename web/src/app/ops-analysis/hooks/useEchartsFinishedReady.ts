import { useCallback, useEffect, useMemo, useRef } from 'react';

interface UseEchartsFinishedReadyOptions {
  loading: boolean;
  isDataReady: boolean;
  onReady?: (ready: boolean) => void;
  /** Extra gate such as a measured container size. Defaults to true. */
  canReportReady?: boolean;
}

export const useEchartsFinishedReady = ({
  loading,
  isDataReady,
  onReady,
  canReportReady = true,
}: UseEchartsFinishedReadyOptions) => {
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;
  const loadingRef = useRef(loading);
  loadingRef.current = loading;
  const isDataReadyRef = useRef(isDataReady);
  isDataReadyRef.current = isDataReady;
  const canReportReadyRef = useRef(canReportReady);
  canReportReadyRef.current = canReportReady;
  const finishedRef = useRef(false);

  useEffect(() => {
    if (loading) {
      finishedRef.current = false;
      return;
    }
    if (!isDataReady) {
      finishedRef.current = false;
      onReady?.(false);
      return;
    }
    if (finishedRef.current && canReportReady) {
      onReady?.(true);
    }
  }, [canReportReady, isDataReady, loading, onReady]);

  const handleChartFinished = useCallback(() => {
    finishedRef.current = true;
    if (
      loadingRef.current ||
      !isDataReadyRef.current ||
      !canReportReadyRef.current
    ) {
      return;
    }
    onReadyRef.current?.(true);
  }, []);

  const onEvents = useMemo(
    () => ({ finished: handleChartFinished }),
    [handleChartFinished],
  );

  return { onEvents };
};
