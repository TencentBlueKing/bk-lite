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
import { App, ConfigProvider } from 'antd';
import { createAntdTheme } from './antd-adapter';
import { applyThemeMode } from './css-adapter';
import { defaultTheme } from './defaults';
import { persistThemeMode, readStoredThemeMode } from './mode-storage';
import type { SemanticColorTokens, ThemeMode } from './contract';

interface ThemeContextValue {
  mode: ThemeMode;
  tokens: SemanticColorTokens;
  setMode: (mode: ThemeMode) => void;
  toggleMode: () => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

const getInitialMode = (): ThemeMode => {
  if (typeof window === 'undefined') {
    return 'light';
  }
  return window.__BK_LITE_THEME_MODE__ || readStoredThemeMode();
};

export const ThemeProvider = ({ children }: { children: ReactNode }) => {
  const [mode, setModeState] = useState<ThemeMode>(getInitialMode);
  const tokens = defaultTheme[mode];

  useLayoutEffect(() => {
    applyThemeMode(mode);
    window.__BK_LITE_THEME_MODE__ = mode;
  }, [mode]);

  const setMode = useCallback((nextMode: ThemeMode) => {
    setModeState(nextMode);
    applyThemeMode(nextMode);
    persistThemeMode(nextMode);
    window.__BK_LITE_THEME_MODE__ = nextMode;
  }, []);

  const toggleMode = useCallback(() => {
    setMode(mode === 'dark' ? 'light' : 'dark');
  }, [mode, setMode]);

  const antdTheme = useMemo(() => createAntdTheme(mode, tokens), [mode, tokens]);
  const value = useMemo(
    () => ({ mode, tokens, setMode, toggleMode }),
    [mode, setMode, toggleMode, tokens]
  );

  return (
    <ThemeContext.Provider value={value}>
      <ConfigProvider theme={antdTheme}>
        {/* App 提供 message/modal/notification 的动态主题上下文，避免静态 API 告警 */}
        <App>{children}</App>
      </ConfigProvider>
    </ThemeContext.Provider>
  );
};

const useThemeContext = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('Theme hooks must be used within ThemeProvider');
  }
  return context;
};

export const useThemeMode = () => {
  const { mode, setMode, toggleMode } = useThemeContext();
  return { mode, setMode, toggleMode };
};

export const useThemeTokens = () => useThemeContext().tokens;
