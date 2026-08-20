'use client';

import React, { useMemo } from 'react';
import { ConfigProvider } from 'antd';
import { useOptionalThemeTokens } from '@/theme';
import { isScreenChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import {
  buildScreenContentTokenStyle,
  createScreenAntdTheme,
} from '@/app/ops-analysis/utils/screenWidgetTokens';
import styles from './screenWidgetThemeProvider.module.scss';

interface ScreenWidgetThemeProviderProps {
  mode?: OpsChartThemeMode;
  children: React.ReactNode;
  className?: string;
}

const ScreenWidgetThemeProvider: React.FC<ScreenWidgetThemeProviderProps> = ({
  mode,
  children,
  className,
}) => {
  const systemTokens = useOptionalThemeTokens();
  const antdTheme = useMemo(
    () => createScreenAntdTheme(mode, systemTokens),
    [mode, systemTokens],
  );
  const contentStyle = useMemo(
    () => buildScreenContentTokenStyle(mode),
    [mode],
  );

  if (!isScreenChartThemeMode(mode) || !antdTheme) {
    return <>{children}</>;
  }

  return (
    <ConfigProvider theme={antdTheme}>
      <div
        data-screen-widget-theme={mode}
        className={`${styles.root} ${className ?? 'h-full min-h-0 w-full'}`}
        style={contentStyle}
      >
        {children}
      </div>
    </ConfigProvider>
  );
};

export default ScreenWidgetThemeProvider;
