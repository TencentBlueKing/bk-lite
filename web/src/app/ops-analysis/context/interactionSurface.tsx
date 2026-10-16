'use client';

import { createContext, useContext, type ReactNode } from 'react';

import { useShareMode } from '@/app/ops-analysis/context/shareMode';
import type { InteractionSurface } from '@/app/ops-analysis/utils/interactionLink';

const InteractionSurfaceContext = createContext<Exclude<InteractionSurface, 'share'>>('view');

export function InteractionSurfaceProvider({
  editing,
  children,
}: {
  editing: boolean;
  children: ReactNode;
}) {
  return (
    <InteractionSurfaceContext.Provider value={editing ? 'edit' : 'view'}>
      {children}
    </InteractionSurfaceContext.Provider>
  );
}

export function useInteractionSurface(): InteractionSurface {
  const shareMode = useShareMode();
  const surface = useContext(InteractionSurfaceContext);
  if (shareMode) return 'share';
  return surface;
}
