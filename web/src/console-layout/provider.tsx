'use client';

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useLayoutEffect,
  useMemo,
  useState,
} from 'react';
import { DEFAULT_CONSOLE_CHROME_LAYOUT, type ConsoleChromeLayout } from './contract';
import { applyConsoleChromeLayout } from './dom';
import { persistConsoleChromeLayout, readStoredConsoleChromeLayout } from './storage';
import { resolveEffectiveChromeLayout } from './resolve';

interface ConsoleLayoutContextValue {
  layout: ConsoleChromeLayout;
  setLayout: (layout: ConsoleChromeLayout) => void;
}

const ConsoleLayoutContext = createContext<ConsoleLayoutContextValue | undefined>(undefined);

const fallbackConsoleLayout: ConsoleLayoutContextValue = {
  layout: DEFAULT_CONSOLE_CHROME_LAYOUT,
  setLayout: () => undefined,
};

const getInitialLayout = (): ConsoleChromeLayout => {
  if (typeof window === 'undefined') {
    return DEFAULT_CONSOLE_CHROME_LAYOUT;
  }
  return window.__BK_LITE_CONSOLE_LAYOUT__ || readStoredConsoleChromeLayout();
};

export const ConsoleLayoutProvider = ({ children }: { children: ReactNode }) => {
  const [layout, setLayoutState] = useState<ConsoleChromeLayout>(getInitialLayout);

  useLayoutEffect(() => {
    applyConsoleChromeLayout(layout);
    window.__BK_LITE_CONSOLE_LAYOUT__ = layout;
  }, [layout]);

  const setLayout = useCallback((nextLayout: ConsoleChromeLayout) => {
    setLayoutState(nextLayout);
    applyConsoleChromeLayout(nextLayout);
    persistConsoleChromeLayout(nextLayout);
    window.__BK_LITE_CONSOLE_LAYOUT__ = nextLayout;
  }, []);

  const value = useMemo(
    () => ({ layout, setLayout }),
    [layout, setLayout],
  );

  return (
    <ConsoleLayoutContext.Provider value={value}>
      {children}
    </ConsoleLayoutContext.Provider>
  );
};

export const useConsoleLayout = () => {
  return useContext(ConsoleLayoutContext) ?? fallbackConsoleLayout;
};

export const useEffectiveChromeLayout = (pathname: string | null | undefined): ConsoleChromeLayout => {
  const { layout } = useConsoleLayout();
  return useMemo(
    () => resolveEffectiveChromeLayout(layout, pathname),
    [layout, pathname],
  );
};
