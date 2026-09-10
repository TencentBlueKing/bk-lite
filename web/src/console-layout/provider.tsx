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
import {
  DEFAULT_CONSOLE_CHROME_LAYOUT,
  DEFAULT_CONSOLE_SIDE_NAV_MODE,
  type ConsoleChromeLayout,
  type ConsoleSideNavMode,
} from './contract';
import { applyConsoleChromeLayout } from './dom';
import {
  persistConsoleChromeLayout,
  persistConsoleSideNavMode,
  readStoredConsoleChromeLayout,
  readStoredConsoleSideNavMode,
} from './storage';
import { resolveEffectiveChromeLayout } from './resolve';

interface ConsoleLayoutContextValue {
  layout: ConsoleChromeLayout;
  setLayout: (layout: ConsoleChromeLayout) => void;
  sideNav: ConsoleSideNavMode;
  setSideNav: (mode: ConsoleSideNavMode) => void;
}

const ConsoleLayoutContext = createContext<ConsoleLayoutContextValue | undefined>(undefined);

const fallbackConsoleLayout: ConsoleLayoutContextValue = {
  layout: DEFAULT_CONSOLE_CHROME_LAYOUT,
  setLayout: () => undefined,
  sideNav: DEFAULT_CONSOLE_SIDE_NAV_MODE,
  setSideNav: () => undefined,
};

const getInitialLayout = (): ConsoleChromeLayout => {
  if (typeof window === 'undefined') {
    return DEFAULT_CONSOLE_CHROME_LAYOUT;
  }
  return window.__BK_LITE_CONSOLE_LAYOUT__ || readStoredConsoleChromeLayout();
};

export const ConsoleLayoutProvider = ({ children }: { children: ReactNode }) => {
  const [layout, setLayoutState] = useState<ConsoleChromeLayout>(getInitialLayout);
  const [sideNav, setSideNavState] = useState<ConsoleSideNavMode>(readStoredConsoleSideNavMode);

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

  const setSideNav = useCallback((mode: ConsoleSideNavMode) => {
    setSideNavState(mode);
    persistConsoleSideNavMode(mode);
  }, []);

  const value = useMemo(
    () => ({ layout, setLayout, sideNav, setSideNav }),
    [layout, setLayout, sideNav, setSideNav],
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
