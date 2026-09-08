'use client';

import { useEffect } from 'react';
import { requestLegacyThirdLoginAuthorize } from '@/utils/legacyThirdLogin';
import { useTranslation } from '@/utils/i18n';
import { PORTAL_HOME_PATH } from '@/utils/route';

interface LegacyThirdLoginAuthorizeBridgeProps {
  callbackUrl?: string;
  thirdLoginCode: string;
  token?: string;
}

export default function LegacyThirdLoginAuthorizeBridge({
  callbackUrl,
  thirdLoginCode,
  token,
}: LegacyThirdLoginAuthorizeBridgeProps) {
  const { t } = useTranslation();

  useEffect(() => {
    let cancelled = false;

    const redirect = async () => {
      const targetUrl = token
        ? await requestLegacyThirdLoginAuthorize({
          callbackUrl: callbackUrl || PORTAL_HOME_PATH,
          thirdLoginCode,
          token,
        })
        : PORTAL_HOME_PATH;
      if (!cancelled) {
        window.location.href = targetUrl;
      }
    };

    void redirect();
    return () => {
      cancelled = true;
    };
  }, [callbackUrl, thirdLoginCode, token]);

  return (
    <div className="flex min-h-screen items-center justify-center px-6 text-center">
      <div>
        <div className="text-lg font-semibold text-(--color-text-1)">
          {t('signin.legacyThirdLogin.title')}
        </div>
        <div className="mt-2 text-sm text-(--color-text-3)">
          {t('signin.legacyThirdLogin.returning')}
        </div>
      </div>
    </div>
  );
}
