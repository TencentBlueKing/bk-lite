'use client';

import { useEffect, useState } from 'react';
import type { ComponentType } from 'react';
import { Spin } from 'antd';

import { useClientData } from '@/context/client';

import { loadAuthorizedCapabilityModules } from './loadAuthorizedModules';
import { collectSlotContributions, resolveSlot } from './slots';

interface AppSlotProps {
  id: string;
  slotKey: string;
  [key: string]: unknown;
}

export default function AppSlot({ id, slotKey, ...props }: AppSlotProps) {
  const { clientData, loading: clientLoading } = useClientData();
  const [Comp, setComp] = useState<ComponentType<Record<string, unknown>> | null>(
    null
  );
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (clientLoading) {
      setReady(false);
      setComp(null);
      return;
    }

    let cancelled = false;
    setReady(false);
    loadAuthorizedCapabilityModules(clientData).then((modules) => {
      if (cancelled) return;
      const slot = resolveSlot(collectSlotContributions(modules, id), slotKey);
      setComp(() => slot?.component ?? null);
      setReady(true);
    });

    return () => {
      cancelled = true;
    };
  }, [clientData, clientLoading, id, slotKey]);

  if (!ready || clientLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spin />
      </div>
    );
  }

  if (!Comp) {
    return null;
  }

  return <Comp {...props} />;
}
