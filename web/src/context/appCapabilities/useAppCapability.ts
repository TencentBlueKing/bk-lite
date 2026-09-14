'use client';

import { useEffect, useState } from 'react';

import { useClientData } from '@/context/client';

import { hasAppAccess } from './access';
import {
  APP_CAPABILITY_LOADERS,
  type AppCapabilityApi,
  type AppCapabilityName,
} from './catalog';
import { loadAuthorizedCapability } from './load';
import type { AppCapabilityState } from './types';

export function useAppCapability<K extends AppCapabilityName>(
  appName: K
): AppCapabilityState<AppCapabilityApi<K>> {
  const { clientData, loading } = useClientData();
  const allowed = hasAppAccess(clientData, appName);
  const [state, setState] = useState<AppCapabilityState<AppCapabilityApi<K>>>({
    status: 'loading',
  });

  useEffect(() => {
    if (loading) {
      return;
    }
    if (!allowed) {
      setState({ status: 'unavailable' });
      return;
    }

    let cancelled = false;
    loadAuthorizedCapability(appName, {
      authorized: true,
      load: APP_CAPABILITY_LOADERS[appName] as () => Promise<AppCapabilityApi<K>>,
    }).then((api) => {
      if (cancelled) return;
      setState((prev) => {
        if (api) {
          if (prev.status === 'ready' && prev.api === api) {
            return prev;
          }
          return { status: 'ready', api: api as AppCapabilityApi<K> };
        }
        if (prev.status === 'unavailable') {
          return prev;
        }
        return { status: 'unavailable' };
      });
    });

    return () => {
      cancelled = true;
    };
  }, [allowed, appName, loading]);

  return state;
}
