'use client';

import { createContext, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import { DashboardRuntimeScheduler } from '@/app/ops-analysis/utils/dashboardRuntimeScheduler';

const DashboardRuntimeSchedulerContext =
  createContext<DashboardRuntimeScheduler | null>(null);

export const DashboardRuntimeSchedulerProvider = ({
  children,
}: {
  children: ReactNode;
}) => {
  const [scheduler] = useState(() => new DashboardRuntimeScheduler());
  const lifecycleRef = useRef(0);

  useEffect(() => {
    const lifecycle = ++lifecycleRef.current;
    return () => {
      queueMicrotask(() => {
        if (lifecycleRef.current === lifecycle) scheduler.destroy();
      });
    };
  }, [scheduler]);

  return (
    <DashboardRuntimeSchedulerContext.Provider value={scheduler}>
      {children}
    </DashboardRuntimeSchedulerContext.Provider>
  );
};

export const useDashboardRuntimeScheduler = () =>
  useContext(DashboardRuntimeSchedulerContext);
