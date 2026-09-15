'use client';

import { useRef } from 'react';

import { useAppCapability } from './useAppCapability';
import {
  appNameForWidgetKey,
  resolveWidgetLoader,
  type AppWidgetKey,
  type AppWidgetLoader,
} from './widgets';

export interface AppWidgetState {
  status: 'unavailable' | 'loading' | 'ready';
  declared: boolean;
  loadWidget: AppWidgetLoader | null;
}

export function useAppWidget(key: AppWidgetKey): AppWidgetState {
  const capability = useAppCapability(appNameForWidgetKey(key));
  const cachedLoaderRef = useRef<AppWidgetLoader | null>(null);
  const cachedKeyRef = useRef(key);

  if (cachedKeyRef.current !== key) {
    cachedLoaderRef.current = null;
    cachedKeyRef.current = key;
  }

  if (capability.status === 'ready') {
    cachedLoaderRef.current = resolveWidgetLoader(capability.api, key);
  } else if (capability.status === 'unavailable') {
    cachedLoaderRef.current = null;
  }

  const loadWidget = cachedLoaderRef.current;
  if (loadWidget) {
    return {
      status: 'ready',
      declared: true,
      loadWidget,
    };
  }
  if (capability.status === 'ready' || capability.status === 'unavailable') {
    return {
      status: 'unavailable',
      declared: false,
      loadWidget: null,
    };
  }
  return {
    status: 'loading',
    declared: false,
    loadWidget: null,
  };
}
