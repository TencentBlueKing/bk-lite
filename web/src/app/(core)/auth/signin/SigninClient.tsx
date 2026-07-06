"use client";
import {ArrowLeftOutlined} from "@ant-design/icons";
import {signIn} from "next-auth/react";
import {useEffect, useState} from "react";
import {Input, Select} from "antd";
import PasswordResetForm from "./PasswordResetForm";
import OtpVerificationForm from "./OtpVerificationForm";
import WechatQrLoginPanel from "./WechatQrLoginPanel";
import {useTheme} from '@/context/theme';
import {usePortalBranding} from "@/hooks/usePortalBranding";
import {useTranslation} from "@/utils/i18n";
import {saveAuthToken} from "@/utils/crossDomainAuth";
import {
  AUTH_POPUP_SUCCESS_MESSAGE,
  buildOauthCallbackBridgeUrl,
  buildPopupSigninUrl,
  buildThirdLoginCallbackUrl,
  buildWechatPopupUrl,
  resolveThirdLoginFlag
} from "@/utils/authRedirect";

interface SigninClientProps {
  searchParams?: {
    callbackUrl: string;
    error: string;
    third_login?: string;
    thirdLogin?: string;
    popup?: string;
    provider?: string;
  };
  signinErrors?: Record<string | "default", string>;
  mode?: 'page' | 'modal';
  onAuthenticated?: () => void;
  showThirdPartyLogin?: boolean;
}

type AuthStep = 'login' | 'reset-password' | 'otp-verification';
type ModalThirdPartyView = 'login' | 'wechat';

interface LoginResponse {
  temporary_pwd?: boolean;
  enable_otp?: boolean;
  qrcode?: boolean;
  token?: string;
  username?: string;
  id?: string;
  locale?: string;
  timezone?: string;
  redirect_url?: string;
  password_expiry_reminder?: string;
  // OTP two-phase authentication fields
  require_otp?: boolean;
  challenge_id?: string;
  qr_code?: string;  // QR code for first-time OTP binding
  need_binding?: boolean;  // Flag indicating first-time OTP binding
}

interface WeChatSettings {
  enabled: boolean;
  app_id?: string;
  app_secret?: string;
  redirect_uri?: string;
}

interface BkSettings {
  is_open_logining: boolean;
  url?: string;
}

export default function SigninClient({
  searchParams,
  signinErrors = {},
  mode = 'page',
  onAuthenticated,
  showThirdPartyLogin = true,
}: SigninClientProps) {
  const callbackUrl = searchParams?.callbackUrl || "/";
  const error = searchParams?.error || "";
  const third_login = searchParams?.third_login;
  const thirdLogin = searchParams?.thirdLogin;
  const popup = searchParams?.popup;
  const provider = searchParams?.provider;
  const thirdLoginFlag = resolveThirdLoginFlag(thirdLogin, third_login);
  const isPopupWindowMode = popup === 'true' || popup === '1';
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [domain, setDomain] = useState("");
  const [domainList, setDomainList] = useState<string[]>([]);
  const [loadingDomains, setLoadingDomains] = useState(true);
  const [formError, setFormError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isWechatBrowser, setIsWechatBrowser] = useState(false);
  const [authStep, setAuthStep] = useState<AuthStep>('login');
  const [loginData, setLoginData] = useState<LoginResponse>({});
  const [qrCodeUrl, setQrCodeUrl] = useState<string>("");
  const [wechatSettings, setWechatSettings] = useState<WeChatSettings | null>(null);
  const { themeName } = useTheme();
  const { logoUrl } = usePortalBranding();
  const { t } = useTranslation();
  const [loadingWechatSettings, setLoadingWechatSettings] = useState(true);
  const [bkSettings, setBkSettings] = useState<BkSettings | null>(null);
  const [loadingBkSettings, setLoadingBkSettings] = useState(true);
  const [hasTriggeredPopupProvider, setHasTriggeredPopupProvider] = useState(false);
  const [modalThirdPartyView, setModalThirdPartyView] = useState<ModalThirdPartyView>('login');
  const isModalMode = mode === 'modal';
  const isDarkTheme = themeName === 'dark';

  useEffect(() => {
    const userAgent = navigator.userAgent.toLowerCase();
    setIsWechatBrowser(userAgent.includes('micromessenger') || userAgent.includes('wechat'));

    // Fetch WeChat settings, BK settings and domain list
    fetchWechatSettings();
    fetchBkSettings();
    fetchDomainList();
  }, []);

  const finishAuthentication = (targetUrl: string) => {
    if (onAuthenticated) {
      onAuthenticated();
      return;
    }

    if (isPopupWindowMode && window.opener && !window.opener.closed) {
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
  };

  const checkExistingAuthentication = async () => {
    try {
      const response = await fetch('/api/proxy/core/api/get_bk_settings/', {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-cache, no-store, must-revalidate',
          Pragma: 'no-cache',
        },
        credentials: 'include',
      });

      const responseData = await response.json();
      const userData = responseData?.data?.user;

      if (response.ok && responseData?.result && userData && (userData.username || userData.id)) {
        await completeAuthentication(userData);
        return true;
      }
    } catch (existingAuthError) {
      console.error('Failed to check existing authentication in popup:', existingAuthError);
    }

    return false;
  };

  const openThirdPartyPopup = (targetProvider: 'wechat' | 'bk') => {
    const popupUrl = targetProvider === 'wechat'
      ? buildWechatPopupUrl({
        callbackUrl: callbackUrl || '/',
        thirdLogin: true,
      })
      : buildPopupSigninUrl({
        callbackUrl: callbackUrl || '/',
        thirdLogin: true,
        provider: targetProvider,
      });

    const width = 520;
    const height = 760;
    const left = window.screenX + Math.max((window.outerWidth - width) / 2, 0);
    const top = window.screenY + Math.max((window.outerHeight - height) / 2, 0);

    const openedWindow = window.open(
      popupUrl,
      'bklite-third-party-login',
      `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
    );

    if (!openedWindow) {
      setFormError(t('signin.errors.popupBlocked'));
      return;
    }

    openedWindow.focus();
  };

  const fetchDomainList = async () => {
    try {
      setLoadingDomains(true);
      const response = await fetch('/api/proxy/core/api/get_domain_list/', {
        method: "GET",
        headers: {
          "Content-Type": "application/json"
        },
      });

      const responseData = await response.json();

      if (response.ok && responseData.result && Array.isArray(responseData.data)) {
        setDomainList(responseData.data);
        // Set default domain if available
        if (responseData.data.length > 0) {
          setDomain(responseData.data[0]);
        }
      } else {
        console.error("Failed to fetch domain list:", responseData);
        setDomainList([]);
      }
    } catch (error) {
      console.error("Failed to fetch domain list:", error);
      setDomainList([]);
    } finally {
      setLoadingDomains(false);
    }
  };

  const fetchWechatSettings = async () => {
    try {
      setLoadingWechatSettings(true);
      const response = await fetch("/api/proxy/core/api/get_wechat_settings/", {
        method: "GET",
        headers: {
          "Content-Type": "application/json"
        },
      });

      const responseData = await response.json();

      if (response.ok && responseData.result) {
        setWechatSettings({
          enabled: true,
          ...responseData.data
        });
      } else {
        setWechatSettings({ enabled: false });
      }
    } catch (error) {
      console.error("Failed to fetch WeChat settings:", error);
      setWechatSettings({ enabled: false });
    } finally {
      setLoadingWechatSettings(false);
    }
  };

  const fetchBkSettings = async () => {
    try {
      setLoadingBkSettings(true);
      const response = await fetch('/api/proxy/core/api/get_bk_settings/', {
        method: "GET",
        headers: {
          "Content-Type": "application/json"
        },
      });

      const responseData = await response.json();

      if (response.ok && responseData.result) {
        setBkSettings({
          is_open_logining: responseData.data.bk_login_open,
          url: responseData.data.url,
        });
      } else {
        setBkSettings({ is_open_logining: false });
      }
    } catch (error) {
      console.error("Failed to fetch BK settings:", error);
      setBkSettings({ is_open_logining: false });
    } finally {
      setLoadingBkSettings(false);
    }
  };

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setFormError("");

    try {
      const response = await fetch('/api/proxy/core/api/login/', {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          username,
          password,
          domain,
        }),
      });

      const responseData = await response.json();

      if (!response.ok || !responseData.result) {
        setFormError(responseData.message || t('signin.errors.loginFailed'));
        setIsLoading(false);
        return;
      }

      const userData = responseData.data;
      setLoginData(userData);

      // Two-phase OTP authentication: require_otp means OTP verification is required
      // OTP must be verified BEFORE password reset (need token for reset API)
      if (userData.require_otp && userData.challenge_id) {
        // If qr_code is included, this is first-time OTP binding
        if (userData.qr_code) {
          setQrCodeUrl(userData.qr_code);
        }
        setAuthStep('otp-verification');
        setIsLoading(false);
        return;
      }

      // Only check temporary_pwd when NOT going through OTP flow
      // (OTP flow will check temporary_pwd after verification)
      if (userData.temporary_pwd) {
        setAuthStep('reset-password');
        setIsLoading(false);
        return;
      }

      // Complete authentication first, then handle redirect_url
      await completeAuthentication(userData);

    } catch (error) {
      console.error("Login error:", error);
      setFormError(t('signin.errors.loginError'));
      setIsLoading(false);
    }
  };

  const handlePasswordResetComplete = async (updatedLoginData: LoginResponse) => {
    setLoginData(updatedLoginData);

    // Two-phase OTP authentication after password reset
    if (updatedLoginData.require_otp && updatedLoginData.challenge_id) {
      if (updatedLoginData.qr_code) {
        setQrCodeUrl(updatedLoginData.qr_code);
      }
      setAuthStep('otp-verification');
      return;
    }

    await completeAuthentication(updatedLoginData);
  };

  const handleOtpVerificationComplete = async (loginData: LoginResponse) => {
    // Check if user needs to reset password after OTP verification
    if (loginData.temporary_pwd) {
      setLoginData(loginData);
      setAuthStep('reset-password');
      return;
    }
    await completeAuthentication(loginData);
  };

  const completeAuthentication = async (userData: LoginResponse) => {
    try {
      const userDataForAuth = {
        id: userData.id || userData.username || 'unknown',
        username: userData.username,
        token: userData.token,
        locale: userData.locale || 'en',
        timezone: userData.timezone || 'Asia/Shanghai',
        temporary_pwd: userData.temporary_pwd || false,
        enable_otp: userData.enable_otp || false,
        qrcode: userData.qrcode || false,
      };

      console.log('Completing authentication with user data:', userDataForAuth);

      if (userData.token) {
        saveAuthToken({
          id: userDataForAuth.id,
          username: userDataForAuth.username || '',
          token: userData.token,
          locale: userDataForAuth.locale,
          timezone: userDataForAuth.timezone,
          temporary_pwd: userDataForAuth.temporary_pwd,
          enable_otp: userDataForAuth.enable_otp,
          qrcode: userDataForAuth.qrcode,
        });
      }

      const result = await signIn("credentials", {
        redirect: false,
        username: userDataForAuth.username,
        password: password,
        skipValidation: 'true',
        userData: JSON.stringify(userDataForAuth),
        callbackUrl: callbackUrl || "/",
      }) as any;

      console.log('SignIn result:', result);

      if (result?.error) {
        console.error('SignIn error:', result.error);
        setFormError(result.error);
        setIsLoading(false);
      } else if (result?.ok) {
        // Store password expiry reminder in sessionStorage for display after redirect
        if (userData.password_expiry_reminder) {
          sessionStorage.setItem('password_expiry_reminder', userData.password_expiry_reminder);
        }

        const targetUrl = buildThirdLoginCallbackUrl(
          userData.redirect_url || callbackUrl || "/",
          userData.token,
          thirdLoginFlag,
        );

        console.log('SignIn successful, redirecting to:', targetUrl);
        finishAuthentication(targetUrl);
      } else {
        console.error('SignIn failed with unknown error');
        setFormError(t('signin.errors.authenticationFailed'));
        setIsLoading(false);
      }
    } catch (error) {
      console.error("Failed to complete authentication:", error);
      setFormError(t('signin.errors.authenticationFailed'));
      setIsLoading(false);
    }
  };

  const handleWechatSignIn = async () => {
    if (mode === 'modal' && !isPopupWindowMode) {
      setModalThirdPartyView('wechat');
      return;
    }

    console.log("Starting WeChat login process...");
    const oauthCallbackUrl = isPopupWindowMode
      ? buildPopupSigninUrl({
        callbackUrl: callbackUrl || '/',
        thirdLogin: true,
        provider: 'wechat',
      })
      : buildOauthCallbackBridgeUrl(callbackUrl || '/', thirdLoginFlag, 'wechat');

    console.log("Callback URL:", oauthCallbackUrl);

    signIn("wechat", {
      callbackUrl: oauthCallbackUrl,
      redirect: true
    });
  };

  const handleBkSignIn = () => {
    if (mode === 'modal' && !isPopupWindowMode) {
      openThirdPartyPopup('bk');
      return;
    }

    if (bkSettings?.url) {
      const currentDomain = window.location.origin;
      const targetCallbackUrl = isPopupWindowMode
        ? `${currentDomain}${buildPopupSigninUrl({
          callbackUrl: callbackUrl || '/',
          thirdLogin: true,
          provider: 'bk',
        })}`
        : currentDomain;
      const bkLoginUrl = `${bkSettings.url}?callbackUrl=${encodeURIComponent(targetCallbackUrl)}`;
      console.log("Redirecting to BK login:", bkLoginUrl);
      window.location.href = bkLoginUrl;
    }
  };

  useEffect(() => {
    if (thirdLoginFlag) {
      return;
    }

    if (!isPopupWindowMode || !provider || hasTriggeredPopupProvider || authStep !== 'login') {
      return;
    }

    if (provider === 'wechat') {
      if (loadingWechatSettings) {
        return;
      }

      if (!wechatSettings?.enabled) {
        setFormError(t('signin.errors.wechatUnavailable'));
        setHasTriggeredPopupProvider(true);
        return;
      }

      setHasTriggeredPopupProvider(true);
      void handleWechatSignIn();
      return;
    }

    if (provider === 'bk') {
      if (loadingBkSettings) {
        return;
      }

      setHasTriggeredPopupProvider(true);
      void (async () => {
        const hasExistingAuth = await checkExistingAuthentication();
        if (!hasExistingAuth) {
          handleBkSignIn();
        }
      })();
    }
  }, [authStep, bkSettings?.is_open_logining, hasTriggeredPopupProvider, isPopupWindowMode, loadingBkSettings, loadingWechatSettings, provider, t, thirdLoginFlag, wechatSettings?.enabled]);

  const renderLoginForm = () => (
    <form onSubmit={handleLoginSubmit} className={`flex w-full flex-col ${isModalMode ? 'space-y-5' : 'space-y-6'}`}>
      <div className={isModalMode ? 'space-y-1.5' : 'space-y-2'}>
        <div className="flex justify-between items-center">
          <label htmlFor="domain" className={`font-medium ${isModalMode ? 'text-[13px] text-(--color-text-1)' : 'text-sm text-(--color-text-1)'}`}>{t('signin.form.domain')}</label>
          {loadingDomains && (
            <div className="w-4 h-4 border-2 border-gray-300 border-t-blue-600 rounded-full animate-spin"></div>
          )}
        </div>
        <Select
          id="domain"
          value={domain || undefined}
          onChange={setDomain}
          placeholder={loadingDomains ? t('signin.form.loadingDomains') : t('signin.form.selectDomain')}
          loading={loadingDomains}
          disabled={loadingDomains}
          className="w-full"
          size="middle"
          style={{ height: isModalMode ? '40px' : '48px' }}
          dropdownStyle={{
            borderRadius: '8px',
            boxShadow: '0 10px 25px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)'
          }}
          options={domainList.map(domainItem => ({
            label: domainItem,
            value: domainItem,
          }))}
          notFoundContent={
            loadingDomains ? (
              <div className="flex items-center justify-center py-4">
                <div className="w-4 h-4 border-2 border-gray-300 border-t-blue-600 rounded-full animate-spin mr-2"></div>
                {t('signin.form.loading')}
              </div>
            ) : (
              <div className="flex items-center justify-center py-4 text-gray-500">
                <svg className="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                {t('signin.form.noDomains')}
              </div>
            )
          }
        />
        {/* Error state indicator */}
        {!loadingDomains && domainList.length === 0 && (
          <p className="text-sm text-amber-600 flex items-center mt-1">
            <svg className="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            {t('signin.form.noDomains')}
          </p>
        )}
      </div>

      <div className={isModalMode ? 'space-y-1.5' : 'space-y-2'}>
        <label htmlFor="username" className={`font-medium ${isModalMode ? 'text-[13px] text-(--color-text-1)' : 'text-sm text-(--color-text-1)'}`}>{t('signin.form.username')}</label>
        <Input
          id="username"
          placeholder={t('signin.form.usernamePlaceholder')}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          size="large"
          required
          className={isModalMode ? 'h-10 rounded-xl' : 'h-12'}
        />
      </div>

      <div className={isModalMode ? 'space-y-1.5' : 'space-y-2'}>
        <label htmlFor="password" className={`font-medium ${isModalMode ? 'text-[13px] text-(--color-text-1)' : 'text-sm text-(--color-text-1)'}`}>{t('signin.form.password')}</label>
        <Input.Password
          id="password"
          placeholder={t('signin.form.passwordPlaceholder')}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          size="large"
          required
          className={isModalMode ? 'h-10 rounded-xl' : 'h-12'}
        />
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className={`w-full text-white font-medium transition-all duration-150 ease-in-out ${isModalMode ? 'h-11 rounded-xl bg-[#246BFD] px-4 text-[14px] shadow-[0_12px_28px_rgba(36,107,253,0.24)] hover:bg-[#1F5DE0]' : 'rounded-lg bg-blue-600 px-4 py-3 shadow hover:-translate-y-0.5 hover:bg-blue-700'} ${isLoading ? 'cursor-not-allowed opacity-70' : ''}`}
      >
        {isLoading ? (
          <span className="flex items-center justify-center">
            <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 718-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 714 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            {t('signin.form.signingIn')}
          </span>
        ) : t('signin.form.signIn')}
      </button>
    </form>
  );

  const renderPasswordResetForm = () => (
    <PasswordResetForm
      username={username}
      loginData={loginData}
      onPasswordReset={handlePasswordResetComplete}
      onError={setFormError}
    />
  );

  const renderOtpVerificationForm = () => (
    <OtpVerificationForm
      username={username}
      loginData={loginData}
      qrCodeUrl={qrCodeUrl}
      onOtpVerification={handleOtpVerificationComplete}
      onError={setFormError}
    />
  );

  const renderWechatLoginSection = () => {
    const isLoading = loadingWechatSettings || loadingBkSettings;
    const hasWechat = wechatSettings?.enabled;
    const hasBkLogin = bkSettings?.is_open_logining;
    const hasAnyLogin = hasWechat || hasBkLogin;

    if (isLoading) {
      return (
        <div className={isModalMode ? 'mt-5' : 'mt-6'}>
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-(--color-border-3)"></div>
            </div>
            <div className={`relative flex justify-center ${isModalMode ? 'text-[12px]' : 'text-sm'}`}>
              <span className={`px-3 ${isModalMode ? 'bg-transparent text-(--color-text-3)' : 'bg-(--color-bg) text-(--color-text-1)'}`}>{t('signin.thirdParty.orContinueWith')}</span>
            </div>
          </div>

          <div className={isModalMode ? 'mt-5 space-y-2.5' : 'mt-6 space-y-3'}>
            <div className={`w-full animate-pulse bg-(--color-fill-2) ${isModalMode ? 'h-10 rounded-xl' : 'h-12 rounded-lg'}`}></div>
            {loadingBkSettings && (
              <div className={`w-full animate-pulse bg-(--color-fill-2) ${isModalMode ? 'h-10 rounded-xl' : 'h-12 rounded-lg'}`}></div>
            )}
          </div>
        </div>
      );
    }

    if (!hasAnyLogin) {
      return null;
    }

    return (
      <div className={isModalMode ? 'mt-5' : 'mt-6'}>
        {isModalMode ? (
          <div className="flex justify-center text-[12px] text-(--color-text-3)">
            <span>{t('signin.thirdParty.orContinueWith')}</span>
          </div>
        ) : (
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-(--color-border-3)"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="bg-(--color-bg) px-3 text-(--color-text-1)">{t('signin.thirdParty.orContinueWith')}</span>
            </div>
          </div>
        )}

        <div className={isModalMode ? 'mt-5 space-y-2.5' : 'mt-6 space-y-3'}>
          {hasWechat && (
            <button
              onClick={handleWechatSignIn}
              className={`flex w-full items-center justify-center font-medium text-white transition-colors duration-200 ${isModalMode ? 'h-11 rounded-xl bg-[#10B14A] px-4 text-[14px] shadow-[0_10px_24px_rgba(16,177,74,0.18)] hover:bg-[#0F9E43]' : 'rounded-lg bg-green-600 px-4 py-3 text-sm shadow-sm hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500'}`}
            >
              {t('signin.thirdParty.wechat')}
            </button>
          )}

          {hasBkLogin && (
            <button
              onClick={handleBkSignIn}
              className={`flex w-full items-center justify-center font-medium text-white transition-colors duration-200 ${isModalMode ? 'h-11 rounded-xl bg-[#246BFD] px-4 text-[14px] shadow-[0_10px_24px_rgba(36,107,253,0.18)] hover:bg-[#1F5DE0]' : 'rounded-lg bg-blue-600 px-4 py-3 text-sm shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500'}`}
            >
              {t('signin.thirdParty.blueking')}
            </button>
          )}
        </div>

        {isWechatBrowser && hasWechat && (
          <div className="mt-4 text-center text-sm text-[#10B14A]">
            {t('signin.thirdParty.wechatBrowserTip')}
          </div>
        )}
      </div>
    );
  };

  const content = (
    <div className={`w-full ${isModalMode ? '' : 'max-w-md'}`} style={isModalMode ? { maxWidth: 388 } : undefined}>
      {mode === 'page' && (
        <div className="text-center mb-10">
          <div className="flex justify-center mb-6">
            <img src={logoUrl} alt="Logo" className="h-14 w-auto object-contain" />
          </div>
          <h2 className="text-3xl font-bold text-(--color-text-1)">
            {authStep === 'login' && t('signin.pageTitle.login')}
            {authStep === 'reset-password' && t('signin.pageTitle.resetPassword')}
            {authStep === 'otp-verification' && t('signin.pageTitle.otpVerification')}
          </h2>
          <p className="text-(--color-text-3) mt-2">
            {authStep === 'login' && t('signin.pageDescription.login')}
            {authStep === 'reset-password' && t('signin.pageDescription.resetPassword')}
            {authStep === 'otp-verification' && t('signin.pageDescription.otpVerification')}
          </p>
        </div>
      )}

      {error && (
        <div className={`mb-6 rounded border text-red-700 ${isModalMode ? 'px-3 py-2.5 text-[12px]' : 'border-l-4 border-red-500 bg-red-50 p-4'}`} style={isModalMode ? { borderColor: isDarkTheme ? 'rgba(239, 68, 68, 0.35)' : '#F5D4D4', background: isDarkTheme ? 'rgba(127, 29, 29, 0.18)' : '#FFF7F7' } : undefined}>
          <p className="font-medium">{signinErrors[error.toLowerCase()] ? t(signinErrors[error.toLowerCase()]) : (signinErrors.default ? t(signinErrors.default) : error)}</p>
        </div>
      )}

      {formError && (
        <div className={`mb-6 rounded border text-red-700 ${isModalMode ? 'px-3 py-2.5 text-[12px]' : 'border-l-4 border-red-500 bg-red-50 p-4'}`} style={isModalMode ? { borderColor: isDarkTheme ? 'rgba(239, 68, 68, 0.35)' : '#F5D4D4', background: isDarkTheme ? 'rgba(127, 29, 29, 0.18)' : '#FFF7F7' } : undefined}>
          <p className="font-medium">{formError}</p>
        </div>
      )}

      {authStep === 'login' && modalThirdPartyView === 'login' && renderLoginForm()}
      {authStep === 'reset-password' && renderPasswordResetForm()}
      {authStep === 'otp-verification' && renderOtpVerificationForm()}

      {authStep === 'login' && mode === 'modal' && modalThirdPartyView === 'wechat' && (
        <div className="pt-1">
          <div className="mx-auto mb-4 flex w-full max-w-52 items-center justify-center">
            <div className="relative w-full">
              <button
                type="button"
                onClick={() => setModalThirdPartyView('login')}
                className="absolute left-0 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-[10px] transition-colors"
                style={{
                  background: isDarkTheme ? 'var(--color-fill-2)' : '#EEF4FF',
                  color: isDarkTheme ? 'var(--color-text-2)' : '#4B73B6',
                }}
                aria-label={t('signin.thirdParty.back')}
              >
                <ArrowLeftOutlined className="text-[9px]" />
              </button>
              <div className="text-center text-[12px] font-normal tracking-normal text-(--color-text-3)">{t('signin.thirdParty.wechatScanTitle')}</div>
            </div>
          </div>
          <WechatQrLoginPanel
            callbackUrl={callbackUrl}
            thirdLogin="true"
          />
        </div>
      )}

      {showThirdPartyLogin && authStep === 'login' && modalThirdPartyView === 'login' && renderWechatLoginSection()}
    </div>
  );

  if (mode === 'modal') {
    return <div className="mx-auto w-full py-1" style={{ maxWidth: 388 }}>{content}</div>;
  }

  return (
    <div className="flex w-[calc(100%+2rem)] h-screen -m-4">
      <div
        className="w-3/5 hidden md:block bg-linear-to-br from-blue-500 to-indigo-700"
        style={{
          backgroundImage: "url('/system-login-bg.jpg')",
          backgroundSize: "cover",
          backgroundPosition: "center"
        }}
      >
      </div>

      <div className="w-full h-full md:w-2/5 flex items-center justify-center p-8 bg-(--bg-color-1) overflow-y-auto">
        <div className="w-full h-full flex items-center justify-center">
          {content}
        </div>
      </div>
    </div>
  );
}
