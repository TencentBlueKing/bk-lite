'use client';

import { useEffect } from 'react';
import { AUTH_POPUP_SUCCESS_MESSAGE, buildThirdLoginCallbackUrl } from '@/utils/authRedirect';
import { saveAuthToken } from '@/utils/crossDomainAuth';

interface PopupAuthBridgeProps {
  callbackUrl?: string;
  thirdLogin?: string;
  user: {
    id: string;
    username?: string;
    token?: string;
    locale?: string;
    temporary_pwd?: boolean;
    enable_otp?: boolean;
    qrcode?: boolean;
  };
}

export default function PopupAuthBridge({ callbackUrl, thirdLogin, user }: PopupAuthBridgeProps) {
  useEffect(() => {
    const targetUrl = buildThirdLoginCallbackUrl(callbackUrl, user.token, thirdLogin);

    if (user.token) {
      saveAuthToken({
        id: user.id,
        username: user.username || '',
        token: user.token,
        locale: user.locale || 'en',
        temporary_pwd: user.temporary_pwd || false,
        enable_otp: user.enable_otp || false,
        qrcode: user.qrcode || false,
      });
    }

    if (window.opener && !window.opener.closed) {
      window.opener.postMessage({
        type: AUTH_POPUP_SUCCESS_MESSAGE,
        targetUrl,
      }, window.location.origin);

      window.setTimeout(() => {
        window.close();
      }, 100);
      return;
    }

    window.location.href = targetUrl;
  }, [callbackUrl, thirdLogin, user]);

  return (
    <div className="flex min-h-screen items-center justify-center px-6 text-center">
      <div>
        <div className="text-lg font-semibold text-(--color-text-1)">登录成功</div>
        <div className="mt-2 text-sm text-(--color-text-3)">正在返回原页面...</div>
      </div>
    </div>
  );
}