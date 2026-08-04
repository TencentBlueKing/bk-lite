'use client';

import React, { createContext, useContext, useMemo } from 'react';

interface WidgetViewportValue {
  scale: number;
}

const DEFAULT_VIEWPORT: WidgetViewportValue = { scale: 1 };
const WidgetViewportContext = createContext<WidgetViewportValue>(DEFAULT_VIEWPORT);

const normalizeScale = (scale?: number) =>
  Number.isFinite(scale) && Number(scale) > 0 ? Number(scale) : 1;

export interface WidgetViewportProviderProps {
  scale?: number;
  children: React.ReactNode;
}

export const WidgetViewportProvider: React.FC<WidgetViewportProviderProps> = ({
  scale,
  children,
}) => {
  const value = useMemo(() => ({ scale: normalizeScale(scale) }), [scale]);
  return (
    <WidgetViewportContext.Provider value={value}>
      {children}
    </WidgetViewportContext.Provider>
  );
};

export const useWidgetViewport = () => useContext(WidgetViewportContext);

export const toCanvasPixels = (visiblePixels: number, scale: number) =>
  visiblePixels / normalizeScale(scale);
