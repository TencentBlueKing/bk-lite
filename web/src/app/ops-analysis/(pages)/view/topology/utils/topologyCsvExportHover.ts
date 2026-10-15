import { useSyncExternalStore } from 'react';

let hoverEnabled = false;
const listeners = new Set<() => void>();

export const setTopologyCsvExportHoverEnabled = (enabled: boolean): void => {
  if (hoverEnabled === enabled) return;
  hoverEnabled = enabled;
  listeners.forEach((listener) => listener());
};

export const useTopologyCsvExportHoverEnabled = (): boolean =>
  useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    () => hoverEnabled,
    () => false,
  );
