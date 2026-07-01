/**
 * 已迁移：该组件属于旧的微信独立扫码登录链路。
 *
 * 自 2026-06-18 signin validation cutover 后，微信登录已收敛到
 * login-auth binding 统一流程（/auth/signin/login-auth/*），
 * 通过微信作为标准 binding provider 完成
 * start_login_auth -> callback -> poll status -> session sync。
 *
 * 本组件不再参与主登录流程，保留仅作为历史参考/兼容兜底，
 * 新需求请直接使用 login-auth validation 链路。
 *
 * 相关文档：docs/superpowers/plans/2026-06-18-signin-validation-cutover.md
 */

'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTheme } from '@/context/theme';

declare global {
  interface Window {
    WxLogin?: new (options: Record<string, unknown>) => unknown;
  }
}

interface WechatQrLoginPanelProps {
  callbackUrl: string;
  thirdLogin?: string;
}

interface WechatSettings {
  enabled: boolean;
  app_id?: string;
}

export default function WechatQrLoginPanel({ callbackUrl, thirdLogin }: WechatQrLoginPanelProps) {
  const [wechatSettings, setWechatSettings] = useState<WechatSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const { themeName } = useTheme();
  const isDarkTheme = themeName === 'dark';
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
    <div className="mx-auto w-full max-w-97">
      <div className="px-3 pb-1 pt-1 text-center">
        {loading ? (
          <div className="py-1">
            <div
              className="mx-auto flex aspect-square w-full max-w-52 items-center justify-center rounded-3xl px-4 text-center"
              style={{
                background: isDarkTheme ? 'rgba(255,255,255,0.04)' : '#F4F7FB',
                boxShadow: isDarkTheme ? '0 10px 24px rgba(0, 0, 0, 0.18)' : '0 10px 24px rgba(148, 163, 184, 0.10)',
              }}
            >
              <div className="text-[11px] leading-5 text-(--color-text-3)">正在加载二维码...</div>
            </div>
          </div>
        ) : error ? (
          <div className="py-1">
            <div
              className="mx-auto flex aspect-square w-full max-w-52 items-center justify-center rounded-3xl px-4 text-center"
              style={{
                background: isDarkTheme ? 'rgba(255,255,255,0.04)' : '#F4F7FB',
                boxShadow: isDarkTheme ? '0 10px 24px rgba(0, 0, 0, 0.18)' : '0 10px 24px rgba(148, 163, 184, 0.10)',
              }}
            >
              <div className="text-[11px] leading-5 text-(--color-text-3)">无法显示二维码</div>
            </div>
          </div>
        ) : (
          <div className="py-1">
            <div
              id="bk-lite-wechat-inline-login-container"
              ref={containerRef}
              className="mx-auto flex items-center justify-center rounded-3xl px-4 py-5"
              style={{
                minHeight: '320px',
                background: isDarkTheme ? 'rgba(255,255,255,0.03)' : '#ffffff',
                boxShadow: isDarkTheme ? '0 14px 30px rgba(0, 0, 0, 0.22)' : '0 14px 30px rgba(148, 163, 184, 0.10)',
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
