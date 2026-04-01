'use client';

import { ArrowLeftOutlined } from '@ant-design/icons';
import { useEffect, useMemo, useRef, useState } from 'react';

declare global {
  interface Window {
    WxLogin?: new (options: Record<string, unknown>) => unknown;
  }
}

interface WechatQrLoginPanelProps {
  callbackUrl: string;
  thirdLogin?: string;
  onBack: () => void;
}

interface WechatSettings {
  enabled: boolean;
  app_id?: string;
}

export default function WechatQrLoginPanel({ callbackUrl, thirdLogin, onBack }: WechatQrLoginPanelProps) {
  const [wechatSettings, setWechatSettings] = useState<WechatSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const containerRef = useRef<HTMLDivElement | null>(null);

  const redirectUri = useMemo(() => {
    if (typeof window === 'undefined') {
      return '';
    }

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
        console.error('Failed to fetch wechat settings:', wechatSettingsError);
        setWechatSettings({ enabled: false });
        setError('微信登录配置获取失败');
      } finally {
        setLoading(false);
      }
    };

    void fetchWechatSettings();
  }, []);

  useEffect(() => {
    if (loading || !wechatSettings?.enabled || !wechatSettings.app_id || !containerRef.current || !redirectUri) {
      return;
    }

    let script: HTMLScriptElement | null = null;

    const mountWechatQr = () => {
      if (!window.WxLogin || !containerRef.current) {
        return;
      }

      containerRef.current.innerHTML = '';
      const state = `bk-lite-${Date.now()}`;

      new window.WxLogin({
        self_redirect: true,
        id: 'bk-lite-wechat-inline-login-container',
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
    } else {
      script = document.createElement('script');
      script.src = 'https://res.wx.qq.com/connect/zh_CN/htmledition/js/wxLogin.js';
      script.async = true;
      script.onload = mountWechatQr;
      script.onerror = () => setError('微信二维码加载失败');
      document.body.appendChild(script);
    }

    return () => {
      if (script && script.parentNode) {
        script.parentNode.removeChild(script);
      }
    };
  }, [loading, redirectUri, wechatSettings]);

  return (
    <div className="mx-auto w-full max-w-md">
      <div className="mb-4 flex justify-end">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1.5 rounded-lg bg-[#EEF4FF] px-3 py-1.5 text-[11px] font-medium text-[#355C9A] transition-colors hover:bg-[#E4EEFF] hover:text-[#24487F]"
        >
          <ArrowLeftOutlined className="text-[12px]" />
          <span>返回账号登录</span>
        </button>
      </div>

      <div className="rounded-3xl border border-[#E6EDF2] bg-white p-5 pt-8 text-center">
        <div className="mb-4 text-center">
          <div className="text-[15px] font-semibold text-(--color-text-1)">微信扫码登录</div>
          <div className="mt-1.5 text-[12px] text-(--color-text-3)">打开微信扫一扫完成登录</div>
        </div>

        {loading ? (
          <div className="py-4">
            <div className="mx-auto flex aspect-square w-full max-w-45 items-center justify-center rounded-2xl bg-[#F3F6FA] px-4 text-center">
              <div className="text-[12px] leading-5 text-(--color-text-3)">正在加载微信二维码...</div>
            </div>
          </div>
        ) : error ? (
          <div className="py-4">
            <div className="mx-auto flex aspect-square w-full max-w-45 items-center justify-center rounded-2xl bg-[#F3F6FA] px-4 text-center">
              <div className="text-[12px] leading-5 text-(--color-text-3)">无法显示微信二维码</div>
            </div>
          </div>
        ) : (
          <div>
            <div
              id="bk-lite-wechat-inline-login-container"
              ref={containerRef}
              className="mx-auto flex items-center justify-center rounded-2xl border border-[#E3EAF0] bg-white px-4 py-5"
              style={{ minHeight: '340px' }}
            />
            <div className="mt-3 text-center text-[11px] leading-5 text-(--color-text-3)">
              扫码成功后会自动返回当前页面。
            </div>
          </div>
        )}
      </div>
    </div>
  );
}