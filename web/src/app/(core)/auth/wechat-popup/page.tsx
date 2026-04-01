'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';

declare global {
  interface Window {
    WxLogin?: new (options: Record<string, unknown>) => unknown;
  }
}

interface WechatSettings {
  enabled: boolean;
  app_id?: string;
}

export default function WechatPopupPage() {
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get('callbackUrl') || '/';
  const thirdLogin = searchParams.get('thirdLogin') || '';
  const [wechatSettings, setWechatSettings] = useState<WechatSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const containerRef = useRef<HTMLDivElement | null>(null);

  const redirectUri = useMemo(() => {
    const redirectSearchParams = new URLSearchParams({ callbackUrl });
    if (thirdLogin === 'true' || thirdLogin === '1') {
      redirectSearchParams.set('thirdLogin', 'true');
    }

    return `${window.location.origin}/auth/wechat-popup/bridge?${redirectSearchParams.toString()}`;
  }, [callbackUrl, thirdLogin]);

  useEffect(() => {
    const fetchWechatSettings = async () => {
      try {
        setLoading(true);
        const response = await fetch('/api/proxy/core/api/get_wechat_settings/', {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
          cache: 'no-store',
        });

        const responseData = await response.json();

        if (!response.ok || !responseData?.result || !responseData?.data?.app_id) {
          setWechatSettings({ enabled: false });
          setError('微信登录当前不可用');
          return;
        }

        setWechatSettings({
          enabled: true,
          app_id: responseData.data.app_id,
        });
      } catch (wechatSettingsError) {
        console.error('Failed to fetch popup wechat settings:', wechatSettingsError);
        setWechatSettings({ enabled: false });
        setError('微信登录配置获取失败');
      } finally {
        setLoading(false);
      }
    };

    void fetchWechatSettings();
  }, []);

  useEffect(() => {
    if (loading || !wechatSettings?.enabled || !wechatSettings.app_id || !containerRef.current) {
      return;
    }

    const mountWechatQr = () => {
      if (!window.WxLogin || !containerRef.current) {
        return;
      }

      containerRef.current.innerHTML = '';
      const state = `bk-lite-${Date.now()}`;

      new window.WxLogin({
        self_redirect: true,
        id: 'bk-lite-wechat-login-container',
        appid: wechatSettings.app_id,
        scope: 'snsapi_login',
        redirect_uri: encodeURIComponent(redirectUri),
        state,
        style: 'black',
        stylelite: '1',
        fast_login: '0',
        color_scheme: 'light',
      });
    };

    if (window.WxLogin) {
      mountWechatQr();
      return;
    }

    const script = document.createElement('script');
    script.src = 'https://res.wx.qq.com/connect/zh_CN/htmledition/js/wxLogin.js';
    script.async = true;
    script.onload = mountWechatQr;
    script.onerror = () => {
      setError('微信二维码加载失败');
    };
    document.body.appendChild(script);

    return () => {
      document.body.removeChild(script);
    };
  }, [loading, redirectUri, wechatSettings]);


  return (
    <div className="flex min-h-screen flex-col bg-(--color-bg-1)">
      <div className="border-b border-(--color-border-1) px-6 py-4 text-center">
        <div className="text-lg font-semibold text-(--color-text-1)">微信登录</div>
        <div className="mt-1 text-sm text-(--color-text-3)">请使用微信扫描二维码完成登录</div>
      </div>

      <div className="flex flex-1 items-center justify-center bg-(--color-fill-1) p-4">
        <div className="w-full max-w-[420px] rounded-2xl border border-(--color-border-1) bg-white px-6 py-8 shadow-lg">
          {loading ? (
            <div className="py-16 text-center text-sm text-(--color-text-3)">正在加载微信二维码...</div>
          ) : error ? (
            <div className="py-12 text-center">
              <div className="text-base font-semibold text-(--color-text-1)">无法显示微信二维码</div>
              <div className="mt-2 text-sm text-(--color-text-3)">{error}</div>
            </div>
          ) : (
            <div>
              <div id="bk-lite-wechat-login-container" ref={containerRef} className="mx-auto flex min-h-[360px] items-center justify-center" />
              <div className="mt-4 text-center text-xs leading-6 text-(--color-text-3)">
                请使用微信扫一扫完成登录，登录成功后该窗口会自动关闭。
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}