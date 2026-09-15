'use client';

import { useEffect, useRef, useState, type ComponentType } from 'react';

import type { AppWidgetLoader } from './widgets';

export function useLazyAppWidget<P = Record<string, unknown>>(options: {
  loadWidget: AppWidgetLoader | null;
  active: boolean;
  reloadKey?: number;
}): {
  Widget: ComponentType<P> | null;
  loadFailed: boolean;
} {
  const { loadWidget, active, reloadKey = 0 } = options;
  const [Widget, setWidget] = useState<ComponentType<P> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const activatedRef = useRef(false);
  const loadedOkRef = useRef(false);
  const loadedReloadKeyRef = useRef<number | null>(null);

  if (active) {
    activatedRef.current = true;
  }

  useEffect(() => {
    if (!loadWidget || !activatedRef.current) {
      return;
    }
    if (loadedOkRef.current && loadedReloadKeyRef.current === reloadKey) {
      return;
    }
    let cancelled = false;
    setLoadFailed(false);
    loadWidget()
      .then((mod) => {
        if (cancelled) return;
        loadedOkRef.current = true;
        loadedReloadKeyRef.current = reloadKey;
        setWidget(() => mod.default as ComponentType<P>);
      })
      .catch(() => {
        if (cancelled) return;
        loadedOkRef.current = false;
        loadedReloadKeyRef.current = null;
        setWidget(null);
        setLoadFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [active, loadWidget, reloadKey]);

  return { Widget, loadFailed };
}
