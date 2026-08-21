'use client';

import { useCallback, useEffect, useState } from 'react';

const isExpandedValue = (value: unknown, fallback: boolean): boolean => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return fallback;
  }
  const expanded = (value as { expanded?: unknown }).expanded;
  return typeof expanded === 'boolean' ? expanded : fallback;
};

export const useHabitExpanded = ({
  enabled = true,
  load,
  save,
  defaultOpen = true,
}: {
  enabled?: boolean;
  load: () => Promise<unknown>;
  save: (value: { expanded: boolean }) => Promise<unknown>;
  defaultOpen?: boolean;
}): [boolean, (open: boolean) => void] => {
  const [open, setOpen] = useState(defaultOpen);

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    load()
      .then((value) => {
        if (!cancelled) setOpen(isExpandedValue(value, defaultOpen));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [defaultOpen, enabled, load]);

  const onToggle = useCallback(
    (next: boolean) => {
      setOpen(next);
      save({ expanded: next }).catch(() => undefined);
    },
    [save]
  );

  return [open, onToggle];
};
