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
  const [state, setState] = useState<AppCapabilityState<AppCapabilityApi<K>>>({
    status: 'loading',
  });

  useEffect(() => {
    if (loading) {
      setState({ status: 'loading' });
      return;
    }

    if (!hasAppAccess(clientData, appName)) {
      setState({ status: 'unavailable' });
      return;
    }

    let cancelled = false;
    setState({ status: 'loading' });
    loadAuthorizedCapability(appName, {
      authorized: true,
      load: APP_CAPABILITY_LOADERS[appName] as () => Promise<AppCapabilityApi<K>>,
    }).then((api) => {
      if (cancelled) return;
      setState(
        api
          ? { status: 'ready', api: api as AppCapabilityApi<K> }
          : { status: 'unavailable' }
      );
    });

    return () => {
      cancelled = true;
    };
  }, [appName, clientData, loading]);

  return state;
}
