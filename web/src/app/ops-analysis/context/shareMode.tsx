'use client';

import { createContext, useContext, type ReactNode } from 'react';

const ShareModeContext = createContext(false);

export function ShareModeProvider({
  value,
  children,
}: {
  value: boolean;
  children: ReactNode;
}) {
  return (
    <ShareModeContext.Provider value={value}>{children}</ShareModeContext.Provider>
  );
}

export function useShareMode() {
  return useContext(ShareModeContext);
}
