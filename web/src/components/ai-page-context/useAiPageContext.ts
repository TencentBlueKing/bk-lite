'use client';

import { useEffect, useRef } from 'react';

import { registerAiPageContext } from './registry';
import type { AiContextProvider } from './types';

export const useAiPageContext = (provider: AiContextProvider, deps: unknown[] = []) => {
  const providerRef = useRef(provider);
  providerRef.current = provider;
  useEffect(() => {
    return registerAiPageContext(() => providerRef.current());
  }, deps);
};
