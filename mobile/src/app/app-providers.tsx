'use client';

import { AuthProvider, useAuth } from '@/context/auth';
import { ConversationProvider } from '@/context/conversation';
import { LocaleProvider } from '@/context/locale';
import { ThemeProvider } from '@/context/theme';
import { MobileNavigationProvider } from '@/navigation/mobile-back';
import {
  MobileAccessGate,
  MobileAvailabilityProvider,
} from '@/platform/availability/context';
import { applyNativeViewportZoomPolicy } from '@/utils/viewportZoom';
import { Fragment, useEffect, type ReactNode } from 'react';

function OrganizationScopeTree({ children }: { children: ReactNode }) {
  const { organizationScope } = useAuth();
  return <Fragment key={organizationScope}>{children}</Fragment>;
}

export function AppProviders({ children }: { children: ReactNode }) {
  useEffect(() => applyNativeViewportZoomPolicy(), []);

  return (
    <MobileNavigationProvider>
      <ThemeProvider>
        <LocaleProvider>
          <AuthProvider>
            <MobileAvailabilityProvider>
              <MobileAccessGate>
                <ConversationProvider>
                  <OrganizationScopeTree>{children}</OrganizationScopeTree>
                </ConversationProvider>
              </MobileAccessGate>
            </MobileAvailabilityProvider>
          </AuthProvider>
        </LocaleProvider>
      </ThemeProvider>
    </MobileNavigationProvider>
  );
}
