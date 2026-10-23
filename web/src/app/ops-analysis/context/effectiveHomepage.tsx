'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useSession } from 'next-auth/react';
import { useUserInfoContext } from '@/context/userInfo';
import { useHomepageApi } from '@/app/ops-analysis/api/homepage';
import type { EffectiveHomepageEntry } from '@/app/ops-analysis/utils/homepageLanding';

interface EffectiveHomepageValue {
  entry: EffectiveHomepageEntry | null;
  refresh: () => Promise<void>;
}

const EMPTY_VALUE: EffectiveHomepageValue = {
  entry: null,
  refresh: async () => {},
};

const EffectiveHomepageContext = createContext<EffectiveHomepageValue | null>(null);

export const EffectiveHomepageProvider = ({ children }: { children: React.ReactNode }) => {
  const { status } = useSession();
  const { loading, selectedGroup } = useUserInfoContext();
  const { getShortcut } = useHomepageApi();
  const [entry, setEntry] = useState<EffectiveHomepageEntry | null>(null);
  const requestSeq = useRef(0);

  const refresh = useCallback(async () => {
    const seq = requestSeq.current + 1;
    requestSeq.current = seq;
    try {
      const data = await getShortcut();
      if (seq !== requestSeq.current) {
        return;
      }
      const dashboardId = Number(data?.dashboard_id);
      setEntry(dashboardId ? { dashboardId } : null);
    } catch {
      if (seq === requestSeq.current) {
        setEntry(null);
      }
    }
  }, [getShortcut]);

  useEffect(() => {
    if (status !== 'authenticated' || loading) {
      return;
    }
    void refresh();
  }, [loading, refresh, selectedGroup?.id, status]);

  const value = useMemo(() => ({ entry, refresh }), [entry, refresh]);

  return (
    <EffectiveHomepageContext.Provider value={value}>
      {children}
    </EffectiveHomepageContext.Provider>
  );
};

export const useEffectiveHomepage = (): EffectiveHomepageValue =>
  useContext(EffectiveHomepageContext) ?? EMPTY_VALUE;
