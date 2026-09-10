'use client';

import { createContext, useContext, type ReactNode } from 'react';
import type { Group } from '@/types/index';
import { useShareMode } from '@/app/ops-analysis/context/shareMode';

export interface ShareOrganizationValue {
  spaceId?: number;
  groupTree: Group[];
}

const ShareOrganizationContext = createContext<ShareOrganizationValue | null>(null);

export function ShareOrganizationProvider({
  value,
  children,
}: {
  value: ShareOrganizationValue;
  children: ReactNode;
}) {
  return (
    <ShareOrganizationContext.Provider value={value}>
      {children}
    </ShareOrganizationContext.Provider>
  );
}

export function useShareOrganization() {
  return useContext(ShareOrganizationContext);
}

export function useShareOrganizationSeed(): string | number | undefined {
  const shareMode = useShareMode();
  const shareOrganization = useShareOrganization();
  if (!shareMode) {
    return undefined;
  }
  const spaceId = shareOrganization?.spaceId;
  if (spaceId === undefined || spaceId === null) {
    return undefined;
  }
  return spaceId;
}
