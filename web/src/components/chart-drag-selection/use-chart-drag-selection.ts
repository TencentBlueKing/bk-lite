import { useCallback, useEffect, useState } from 'react';
import type { Dayjs } from 'dayjs';

type ActiveLabel = number | string;

interface UseChartDragSelectionOptions<T extends ActiveLabel> {
  enabled?: boolean;
  requireDistinctRange?: boolean;
  onRangeChange?: (range: [Dayjs, Dayjs]) => void;
  toRange: (start: T, end: T) => [Dayjs, Dayjs];
  isValidLabel?: (label: unknown) => label is T;
}

const defaultIsValidLabel = (label: unknown): label is ActiveLabel =>
  typeof label === 'number' || typeof label === 'string';

export const useChartDragSelection = <T extends ActiveLabel>({
  enabled = true,
  requireDistinctRange = false,
  onRangeChange,
  toRange,
  isValidLabel = defaultIsValidLabel as (label: unknown) => label is T,
}: UseChartDragSelectionOptions<T>) => {
  const [startX, setStartX] = useState<T | null>(null);
  const [endX, setEndX] = useState<T | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleMouseUp = useCallback(() => {
    if (!enabled) return;
    setIsDragging(false);
    document.body.style.userSelect = '';

    if (startX !== null && endX !== null) {
      if (!requireDistinctRange || startX !== endX) {
        onRangeChange?.(toRange(startX, endX));
      }
    }

    setStartX(null);
    setEndX(null);
  }, [enabled, endX, onRangeChange, requireDistinctRange, startX, toRange]);

  useEffect(() => {
    if (!enabled) return;

    const handleGlobalMouseUp = () => {
      if (isDragging) {
        handleMouseUp();
      }
    };

    window.addEventListener('mouseup', handleGlobalMouseUp);
    return () => {
      window.removeEventListener('mouseup', handleGlobalMouseUp);
    };
  }, [enabled, handleMouseUp, isDragging]);

  const handleMouseDown = useCallback(
    (event: { activeLabel?: unknown }) => {
      if (!enabled) return;
      const activeLabel = event?.activeLabel;
      if (!isValidLabel(activeLabel)) return;

      setStartX(activeLabel);
      setEndX(null);
      setIsDragging(true);
      document.body.style.userSelect = 'none';
    },
    [enabled, isValidLabel]
  );

  const handleMouseMove = useCallback(
    (event: { activeLabel?: unknown }) => {
      if (!enabled || !isDragging) return;
      const activeLabel = event?.activeLabel;
      if (!isValidLabel(activeLabel)) return;

      setEndX(activeLabel);
    },
    [enabled, isDragging, isValidLabel]
  );

  return {
    startX,
    endX,
    isDragging,
    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
  };
};
