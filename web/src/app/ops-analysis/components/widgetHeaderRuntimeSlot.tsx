'use client';

import React, { createContext, useContext, useState } from 'react';

const WidgetHeaderRuntimeSlotContext = createContext<HTMLElement | null>(null);

export const useWidgetHeaderRuntimeSlot = () =>
  useContext(WidgetHeaderRuntimeSlotContext);

export const WidgetHeaderRuntimeSlotProvider: React.FC<{
  children: (
    slotRef: React.Dispatch<React.SetStateAction<HTMLElement | null>>,
  ) => React.ReactNode;
}> = ({ children }) => {
  const [target, setTarget] = useState<HTMLElement | null>(null);

  return (
    <WidgetHeaderRuntimeSlotContext.Provider value={target}>
      {children(setTarget)}
    </WidgetHeaderRuntimeSlotContext.Provider>
  );
};
