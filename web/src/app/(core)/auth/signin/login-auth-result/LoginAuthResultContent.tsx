'use client';

import { useState } from 'react';
import { CheckOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import { LOGIN_AUTH_RESULT_RETURN_MESSAGE, SIGNIN_WINDOW_NAME } from '@/utils/authRedirect';
import { useTranslation } from '@/utils/i18n';
import type { LoginAuthResultStatus } from '../login-auth/types';

interface LoginAuthResultContentProps {
  status: LoginAuthResultStatus;
  message?: string;
}

const TITLE_KEYS: Record<LoginAuthResultStatus, string> = {
  success: 'signin.loginAuth.result.titleSuccess',
  cancelled: 'signin.loginAuth.result.titleCancelled',
  expired: 'signin.loginAuth.result.titleExpired',
  failed: 'signin.loginAuth.result.titleFailed',
};

function returnToSigninTab() {
  const opener = window.opener;
  if (!opener || opener.closed) {
    return;
  }

  try {
    opener.postMessage(
      { type: LOGIN_AUTH_RESULT_RETURN_MESSAGE },
      window.location.origin,
    );
  } catch {
    // Cross-origin openers cannot receive the message.
  }

  let namedWindow = false;
  try {
    opener.name = SIGNIN_WINDOW_NAME;
    namedWindow = opener.name === SIGNIN_WINDOW_NAME;
  } catch {
    // Cross-origin openers cannot be renamed.
  }

  try {
    opener.focus();
  } catch {
    // Some browsers throw when the opener is cross-origin.
  }

  if (!namedWindow) {
    return;
  }

  try {
    window.open('', SIGNIN_WINDOW_NAME);
  } catch {
    // Named-window focus is best-effort after the user has switched tabs.
  }
}

export default function LoginAuthResultContent({
  status,
  message,
}: LoginAuthResultContentProps) {
  const { t } = useTranslation();
  const [closeFailed, setCloseFailed] = useState(false);
  const isSuccess = status === 'success';
  const description = message?.trim() || t('signin.loginAuth.result.defaultMessage');

  const handleCloseTab = () => {
    returnToSigninTab();
    window.close();
    setCloseFailed(true);
  };

  return (
    <div className="fixed inset-0 flex items-center justify-center px-6 py-8 text-center">
      <div className="w-full max-w-[420px] rounded-[28px] bg-(--color-bg) px-8 py-9 shadow-[0_18px_44px_rgba(15,35,95,0.10)]">
        <div
          className={`mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full text-2xl font-bold text-white ${
            isSuccess ? 'bg-(--color-success)' : 'bg-(--color-fail)'
          }`}
        >
          {isSuccess ? <CheckOutlined aria-hidden /> : <ExclamationCircleOutlined aria-hidden />}
        </div>
        <h1 className="mb-3 text-[32px] font-semibold leading-none text-(--color-text-1)">
          {t(TITLE_KEYS[status])}
        </h1>
        <p className="m-0 whitespace-pre-wrap text-[15px] leading-7 text-(--color-text-2)">
          {description}
        </p>
        <Button className="mt-6 h-10 min-w-[160px]" type="primary" onClick={handleCloseTab}>
          {t('signin.loginAuth.result.closeTab')}
        </Button>
        {closeFailed ? (
          <p className="mt-3 mb-0 text-xs leading-5 text-(--color-text-3)" role="status">
            {t('signin.loginAuth.result.closeFailed')}
          </p>
        ) : null}
      </div>
    </div>
  );
}
