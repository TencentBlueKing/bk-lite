'use client';

import { useEffect, useMemo, useState } from 'react';

import { useClientData } from '@/context/client';
import { useTranslation } from '@/utils/i18n';

import { loadAuthorizedCapabilityModules } from './loadAuthorizedModules';
import { collectSlotContributions } from './slots';
import type { AppSlotContribution } from './types';

export interface AppSlotTabItem {
  key: string;
  label: string;
}

export function useAppSlotTabs(slotId: string): {
  tabs: AppSlotTabItem[];
  loading: boolean;
} {
  const { clientData, loading: clientLoading } = useClientData();
  const { t } = useTranslation();
  const [contributions, setContributions] = useState<
    Array<AppSlotContribution & { appName: string }>
  >([]);
  const [slotsLoading, setSlotsLoading] = useState(true);

  useEffect(() => {
    if (clientLoading) {
      setContributions([]);
      setSlotsLoading(true);
      return;
    }

    let cancelled = false;
    setSlotsLoading(true);
    loadAuthorizedCapabilityModules(clientData).then((modules) => {
      if (cancelled) return;
      setContributions(collectSlotContributions(modules, slotId));
      setSlotsLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [clientData, clientLoading, slotId]);

  const tabs = useMemo(
    () =>
      contributions.map((item) => ({
        key: item.key,
        label: t(item.labelKey, item.labelDefault),
      })),
    [contributions, t]
  );

  return { tabs, loading: clientLoading || slotsLoading };
}
