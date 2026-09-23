'use client';

import { AuthProvider, useAuth } from '@/context/auth';
import { ConversationProvider } from '@/context/conversation';
import { LocaleProvider, useLocale } from '@/context/locale';
import { ThemeProvider } from '@/context/theme';
import { MobileNavigationProvider } from '@/navigation/mobile-back';
import {
  MobileAccessGate,
  MobileAvailabilityProvider,
} from '@/platform/availability/context';
import { useTranslation } from '@/utils/i18n';
import { applyNativeViewportZoomPolicy } from '@/utils/viewportZoom';
import { Fragment, useEffect, type ReactNode } from 'react';

function DocumentLocale() {
  const { locale } = useLocale();
  const { t } = useTranslation();

  useEffect(() => {
    document.title = t('common.portalTitle');

    let description = document.querySelector('meta[name="description"]');
    if (!description) {
      description = document.createElement('meta');
      description.setAttribute('name', 'description');
      document.head.appendChild(description);
    }
    description.setAttribute('content', t('common.portalDescription'));
    document.documentElement.lang = locale.startsWith('en') ? 'en' : 'zh-Hans';
  }, [locale, t]);

  return null;
}

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
          <DocumentLocale />
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
