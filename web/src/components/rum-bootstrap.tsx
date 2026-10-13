'use client';

import { useSession } from 'next-auth/react';
import { useEffect } from 'react';

import { readRumBootstrapConfig } from '@/utils/rumBootstrap';

type RumFaro = {
  api: {
    setUser: (user: { id: string }) => void;
  };
};

declare global {
  interface Window {
    initCoreRum?: (config: {
      app: { name: string; environment?: string };
      endpoint: string;
      apiKey: string;
      replay?: false;
    }) => RumFaro;
    __bkliteRum?: RumFaro;
  }
}

let starting: Promise<RumFaro | undefined> | null = null;

const ensureRum = () => {
  if (starting) {
    return starting;
  }
  const config = readRumBootstrapConfig();
  if (!config || typeof window === 'undefined') {
    return Promise.resolve(undefined);
  }
  starting = new Promise((resolve) => {
    const start = () => {
      if (!window.initCoreRum || window.__bkliteRum) {
        resolve(window.__bkliteRum);
        return;
      }
      window.__bkliteRum = window.initCoreRum({
        app: { name: config.app, environment: config.environment },
        endpoint: config.endpoint,
        apiKey: config.apiKey,
        replay: false,
      });
      resolve(window.__bkliteRum);
    };
    if (window.initCoreRum) {
      start();
      return;
    }
    const script = document.createElement('script');
    script.src = '/rum/bklite-rum-sdk.js';
    script.async = true;
    script.onload = start;
    script.onerror = () => resolve(undefined);
    document.head.appendChild(script);
  });
  return starting;
};

const RumBootstrap = () => {
  const { data: session } = useSession();

  useEffect(() => {
    void ensureRum();
  }, []);

  useEffect(() => {
    const userId = session?.user?.username || session?.user?.id;
    if (!userId) {
      return;
    }
    void ensureRum().then((faro) => {
      faro?.api.setUser({ id: userId });
    });
  }, [session]);

  return null;
};

export default RumBootstrap;
