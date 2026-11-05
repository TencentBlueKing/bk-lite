'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { getSession, signIn, signOut } from 'next-auth/react';
import { MobileAppLoading } from '@/components/mobile-feedback';
import { completeBrowserExternalLogin } from '@/auth/im-login/browser';
import { writeLoginNotice } from '@/auth/im-login/notices';
import { useTranslation } from '@/utils/i18n';
import { withBasePath } from '@/utils/basePath';

export default function ExternalLoginReturnPage() {
  const router = useRouter();
  const { t } = useTranslation();

  useEffect(() => {
    let active = true;
    completeBrowserExternalLogin({
      signIn: (provider, options) => signIn(provider, options),
      getSession,
      signOut: (options) => signOut(options),
    }).then((outcome) => {
      if (!active) return;
      if (outcome.status === 'success') {
        window.location.replace(withBasePath('/'));
        return;
      }
      writeLoginNotice(window.sessionStorage, outcome.notice);
      router.replace('/login');
    }).catch(() => {
      if (!active) return;
      writeLoginNotice(window.sessionStorage, { reason: 'oauth_failed', name: '' });
      router.replace('/login');
    });
    return () => {
      active = false;
    };
  }, [router]);

  return <MobileAppLoading label={t('login.externalReturning')} />;
}
