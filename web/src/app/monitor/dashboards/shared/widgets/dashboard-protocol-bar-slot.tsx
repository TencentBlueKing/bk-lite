'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from 'react';
import { createPortal } from 'react-dom';

interface DashboardProtocolBarSlotContextValue {
  slot: HTMLElement | null;
  setSlot: (node: HTMLElement | null) => void;
}

const DashboardProtocolBarSlotContext =
  createContext<DashboardProtocolBarSlotContextValue | null>(null);

export function DashboardProtocolBarSlotProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  const value = useMemo(() => ({ slot, setSlot }), [slot]);

  return (
    <DashboardProtocolBarSlotContext.Provider value={value}>
      {children}
    </DashboardProtocolBarSlotContext.Provider>
  );
}

/** 挂在实例卡片下方，供 layout 级 CollectProtocolBar portal 定位。 */
export function DashboardProtocolBarSlot() {
  const context = useContext(DashboardProtocolBarSlotContext);
  const setSlotRef = useCallback(
    (node: HTMLDivElement | null) => {
      context?.setSlot(node);
    },
    [context],
  );

  return <div ref={setSlotRef} />;
}

export function DashboardProtocolBarPortal({
  children,
}: {
  children: React.ReactNode;
}) {
  const context = useContext(DashboardProtocolBarSlotContext);
  if (!context?.slot) return null;
  return createPortal(children, context.slot);
}
