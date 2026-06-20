'use client';

import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { signIn } from 'next-auth/react';
import { AUTH_POPUP_SUCCESS_MESSAGE, buildThirdLoginCallbackUrl, resolveThirdLoginFlag } from '@/utils/authRedirect';
import { saveAuthToken } from '@/utils/crossDomainAuth';

export default function WechatPopupBridgePage() {
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get('callbackUrl') || '/';
  const thirdLogin = resolveThirdLoginFlag(searchParams.get('thirdLogin'));
  const code = searchParams.get('code') || '';
  const [loginError, setLoginError] = useState<string | null>(null);

  useEffect(() => {
    if (!code) {
      const oauthError = searchParams.get('error');
      setLoginError(oauthError ? `微信授权失败：${oauthError}` : '未获取到微信授权码，请关闭弹窗后重试');
      return;
    }

    const completeWechatPopupLogin = async () => {
      const exchangeResponse = await fetch('/api/wechat-popup-login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ code }),
      });

      const exchangeData = await exchangeResponse.json();

      if (!exchangeResponse.ok || !exchangeData?.result || !exchangeData?.data) {
        throw new Error(exchangeData?.message || '微信登录失败');
      }

      const user = exchangeData.data;

      if (user.token) {
        saveAuthToken({
          id: user.id,
          username: user.username || '',
          token: user.token,
          locale: user.locale || 'en',
          timezone: user.timezone || 'Asia/Shanghai',
          temporary_pwd: user.temporary_pwd || false,
          enable_otp: user.enable_otp || false,
          qrcode: user.qrcode || false,
        });
      }

      const signInResult = await signIn('credentials', {
        redirect: false,
        username: user.username,
        password: '',
        skipValidation: 'true',
        userData: JSON.stringify(user),
        callbackUrl,
      }) as { ok?: boolean; error?: string } | undefined;

      if (signInResult?.error || !signInResult?.ok) {
        throw new Error(signInResult?.error || '微信登录会话创建失败');
      }

      const targetUrl = buildThirdLoginCallbackUrl(callbackUrl, user.token, thirdLogin);
      const messagePayload = {
        type: AUTH_POPUP_SUCCESS_MESSAGE,
        targetUrl,
      };

      if (window.parent && window.parent !== window) {
        window.parent.postMessage(messagePayload, window.location.origin);
        return;
      }

      if (window.opener && !window.opener.closed) {
        window.opener.postMessage(messagePayload, window.location.origin);
        window.setTimeout(() => {
          window.close();
        }, 100);
        return;
      }

      window.location.href = targetUrl;
    };

    void completeWechatPopupLogin().catch((error) => {
      console.error('Failed to complete wechat popup login:', error);
      setLoginError((error as Error)?.message || '微信登录失败，请关闭弹窗后重试');
    });
  }, [callbackUrl, code, searchParams, thirdLogin]);

  if (loginError) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6 text-center">
        <div>
          <div className="text-lg font-semibold text-(--color-text-1)">微信登录失败</div>
          <div className="mt-2 text-sm text-(--color-text-3)">{loginError}</div>
          <button
            className="mt-4 rounded px-4 py-2 text-sm text-(--color-primary) underline"
            onClick={() => window.close()}
          >
            关闭并重试
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-6 text-center">
      <div>
        <div className="text-lg font-semibold text-(--color-text-1)">正在完成微信登录</div>
        <div className="mt-2 text-sm text-(--color-text-3)">请稍候，登录成功后将自动返回原页面。</div>
      </div>
    </div>
  );
}
