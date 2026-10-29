'use client';

import {
  createContext,
  useContext,
  type ReactNode,
} from 'react';
import type { DashboardScenePermissionCode } from '@/app/ops-analysis/utils/dashboardWidgetAuth';

export interface DashboardViewAuthContextValue {
  frozen: boolean;
  scenePermissions: Record<string, DashboardScenePermissionCode>;
  isWidgetUnauthorized: (widgetId: string) => boolean;
  isScenePermissionDenied: (widgetId: string) => boolean;
}

const DashboardViewAuthContext = createContext<DashboardViewAuthContextValue | null>(
  null,
);

export const DashboardViewAuthProvider = ({
  children,
  value,
}: {
  children: ReactNode;
  value: DashboardViewAuthContextValue;
}) => (
  <DashboardViewAuthContext.Provider value={value}>
    {children}
  </DashboardViewAuthContext.Provider>
);

export const useDashboardViewAuth = (): DashboardViewAuthContextValue | null =>
  useContext(DashboardViewAuthContext);
