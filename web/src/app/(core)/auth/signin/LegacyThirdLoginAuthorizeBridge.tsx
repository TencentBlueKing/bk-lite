'use client';

import { useEffect, useState } from 'react';
import { Button } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';
import { requestLegacyThirdLoginAuthorize } from '@/utils/legacyThirdLogin';
import { useTranslation } from '@/utils/i18n';
import { PORTAL_HOME_PATH } from '@/utils/route';
import SigninPageFrame from './login-auth/SigninPageFrame';

interface LegacyThirdLoginAuthorizeBridgeProps {
  callbackUrl?: string;
  thirdLoginCode: string;
  token?: string;
}

const MANUAL_CONTINUE_DELAY_MS = 3000;

export default function LegacyThirdLoginAuthorizeBridge({
  callbackUrl,
  thirdLoginCode,
  token,
}: LegacyThirdLoginAuthorizeBridgeProps) {
  const { t } = useTranslation();
  const [targetUrl, setTargetUrl] = useState<string | null>(null);
  const [showContinue, setShowContinue] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setShowContinue(true);
    }, MANUAL_CONTINUE_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const redirect = async () => {
      const url = token
        ? await requestLegacyThirdLoginAuthorize({
          callbackUrl: callbackUrl || PORTAL_HOME_PATH,
          thirdLoginCode,
          token,
        })
        : PORTAL_HOME_PATH;
      if (cancelled) {
        return;
      }
      setTargetUrl(url);
      window.location.replace(url);
    };

    void redirect();
    return () => {
      cancelled = true;
    };
  }, [callbackUrl, thirdLoginCode, token]);

  return (
    <SigninPageFrame title={t('signin.legacyThirdLogin.title')}>
      <div className="text-center" aria-live="polite">
        <LoadingOutlined
          aria-hidden
          className="text-xl text-(--color-primary)"
        />
        <p className="mt-3 text-sm text-(--color-text-3)">
          {t('signin.legacyThirdLogin.returning')}
        </p>
        {showContinue ? (
          <Button
            type="link"
            className="mt-1 px-0"
            onClick={() => {
              window.location.replace(targetUrl || PORTAL_HOME_PATH);
            }}
          >
            {t('signin.legacyThirdLogin.continue')}
          </Button>
        ) : null}
      </div>
    </SigninPageFrame>
  );
}
