'use client';

import '@/polyfills/react-dom';
import { AuthProvider } from '@/context/auth';
import { ConversationProvider } from '@/context/conversation';
import { LocaleProvider } from '@/context/locale';
import { ThemeProvider } from '@/context/theme';
import { MobileNavigationProvider } from '@/navigation/mobile-back';
import type { ReactNode } from 'react';

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <MobileNavigationProvider>
      <ThemeProvider>
        <LocaleProvider>
          <AuthProvider>
            <ConversationProvider>{children}</ConversationProvider>
          </AuthProvider>
        </LocaleProvider>
      </ThemeProvider>
    </MobileNavigationProvider>
  );
}
