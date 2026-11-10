'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  browserStorage,
  readHideEmptyModels,
  writeHideEmptyModels,
} from '@/utils/emptyModelTree';

export const useHideEmptyModelPreference = (storageKey: string) => {
  const [hideEmptyModels, setHideEmptyModels] = useState(false);
  const hideEmptyModelsRef = useRef(false);
  const [preferenceReady, setPreferenceReady] = useState(false);

  useEffect(() => {
    const stored = readHideEmptyModels(browserStorage(), storageKey);
    hideEmptyModelsRef.current = stored;
    setHideEmptyModels(stored);
    setPreferenceReady(true);
  }, [storageKey]);

  const updateHideEmptyModels = useCallback((next: boolean) => {
    hideEmptyModelsRef.current = next;
    setHideEmptyModels(next);
    writeHideEmptyModels(browserStorage(), storageKey, next);
  }, [storageKey]);

  return {
    hideEmptyModels,
    hideEmptyModelsRef,
    preferenceReady,
    updateHideEmptyModels,
  };
};
