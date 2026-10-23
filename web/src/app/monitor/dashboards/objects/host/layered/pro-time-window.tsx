'use client';

import React, { createContext, useContext, useMemo } from 'react';
import type { TimeValuesProps } from '@/app/monitor/types';
import {
  isProChartWindowPending,
  selectProChartWindow,
  type ProChartWindow
} from '../../../shared/utils/pro-chart-window';

export interface ProTimeContextValue {
  window: ProChartWindow | null;
  /** 顶栏窗口正在重查时，折线和事件条先显示「加载中」，不把上一窗的序列留在新轴上。 */
  suspend: boolean;
}

const ProTimeContext = createContext<ProTimeContextValue | null>(null);

export function ProTimeWindowProvider({
  timeValues,
  queryTimeRange,
  suspend = false,
  children
}: {
  timeValues: TimeValuesProps;
  queryTimeRange?: { startMs: number; endMs: number } | null;
  suspend?: boolean;
  children: React.ReactNode;
}) {
  const chartWindow = useMemo(
    () => selectProChartWindow(timeValues, queryTimeRange),
    [queryTimeRange, timeValues]
  );
  const pending = useMemo(
    () => isProChartWindowPending(timeValues, queryTimeRange),
    [queryTimeRange, timeValues]
  );
  const value = useMemo(
    () => ({ window: chartWindow, suspend: suspend || pending }),
    [chartWindow, pending, suspend]
  );
  return <ProTimeContext.Provider value={value}>{children}</ProTimeContext.Provider>;
}

export function useProTimeWindow() {
  return useContext(ProTimeContext);
}
