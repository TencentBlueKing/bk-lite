'use client';

import React, { createContext, useContext, useMemo } from 'react';

import type { ScreenRenderContext } from '@/app/ops-analysis/types/dashBoard';
import {
  clampInteractionMenuScale,
  resolveInteractionMenuScale,
} from '@/app/ops-analysis/utils/interactionMenuScale';

const InteractionMenuScaleContext = createContext(1);

export function InteractionMenuScaleProvider({
  context,
  scale,
  children,
}: {
  context?: ScreenRenderContext | null;
  /** 调用方已经算好的倍数，例如机柜卡的屏幕字号倍数。有它时不再从大屏 context 推。 */
  scale?: number;
  children: React.ReactNode;
}) {
  const value = useMemo(
    () => (
      typeof scale === 'number'
        ? clampInteractionMenuScale(scale)
        : resolveInteractionMenuScale(context)
    ),
    [context, scale],
  );
  return (
    <InteractionMenuScaleContext.Provider value={value}>
      {children}
    </InteractionMenuScaleContext.Provider>
  );
}

export const useInteractionMenuScale = () => useContext(InteractionMenuScaleContext);
