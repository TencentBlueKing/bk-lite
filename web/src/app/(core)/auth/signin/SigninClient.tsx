"use client";
import {signIn} from "next-auth/react";
import type { SignInResponse } from "next-auth/react";
import {useState} from "react";
import PasswordResetForm from "./PasswordResetForm";
import OtpVerificationForm from "./OtpVerificationForm";
import BuiltinSigninContent from "./login-auth/BuiltinSigninContent";
import LoginAuthBindingContent from "./login-auth/LoginAuthBindingContent";
import LoginAuthValidationPanel from "./login-auth/LoginAuthValidationPanel";
import SigninContentShell from "./login-auth/SigninContentShell";
import { getBindingPasswordCopy } from "./login-auth/bindingPasswordCopy";
import { useLoginAuthValidation } from "./login-auth/useLoginAuthValidation";
import {
  isBindingSelectionLocked,
  resolveInlineValidationError,
  resolveSigninSurface,
  shouldShowBindingsSelector,
} from "./login-auth/orderedBindingState";
import {useTheme} from '@/context/theme';
import {usePortalBranding} from "@/hooks/usePortalBranding";
import {useTranslation} from "@/utils/i18n";
import {saveAuthToken} from "@/utils/crossDomainAuth";
import {
  AUTH_POPUP_SUCCESS_MESSAGE,
  buildThirdLoginCallbackUrl,
  resolveThirdLoginFlag
} from "@/utils/authRedirect";
import type { LoginAuthLoginResult } from "./login-auth/types";

interface SigninClientProps {
  searchParams?: {
    callbackUrl: string;
    error: string;
    third_login?: string;
    thirdLogin?: string;
    popup?: string;
  };
  signinErrors?: Record<string | "default", string>;
  mode?: 'page' | 'modal';
  onAuthenticated?: () => void;
}

type AuthStep = 'login' | 'reset-password' | 'otp-verification';

interface LoginResponse {
  temporary_pwd?: boolean;
  enable_otp?: boolean;
  qrcode?: boolean;
  token?: string;
  username?: string;
  display_name?: string;
  domain?: string;
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

const VALIDATION_MODE_DEFAULT_DOMAIN = "domain.com";

export default function SigninClient({
  searchParams,
  signinErrors = {},
  mode = 'page',
  onAuthenticated,
}: SigninClientProps) {
  const callbackUrl = searchParams?.callbackUrl || "/";
  const error = searchParams?.error || "";
  const third_login = searchParams?.third_login;
  const thirdLogin = searchParams?.thirdLogin;
  const popup = searchParams?.popup;
  const thirdLoginFlag = resolveThirdLoginFlag(thirdLogin, third_login);
  const isPopupWindowMode = popup === 'true' || popup === '1';
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [bindingCredentialMap, setBindingCredentialMap] = useState<Record<number, { username: string; password: string }>>({});
  const [formError, setFormError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [authStep, setAuthStep] = useState<AuthStep>('login');
  const [loginData, setLoginData] = useState<LoginResponse>({});
  const [qrCodeUrl, setQrCodeUrl] = useState<string>("");
  const { themeName } = useTheme();
  const { logoUrl } = usePortalBranding();
  const { t } = useTranslation();
  const isModalMode = mode === 'modal';
  const isDarkTheme = themeName === 'dark';

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

  const applyOtpLoginResult = (otpLoginResult: LoginAuthLoginResult) => {
    setUsername(otpLoginResult.username || "");
    setLoginData({
      id: otpLoginResult.id ? String(otpLoginResult.id) : undefined,
      username: otpLoginResult.username,
      display_name: otpLoginResult.display_name,
      domain: otpLoginResult.domain,
      locale: otpLoginResult.locale,
      timezone: otpLoginResult.timezone,
      token: otpLoginResult.token,
      temporary_pwd: otpLoginResult.temporary_pwd,
      enable_otp: otpLoginResult.enable_otp,
      password_expiry_reminder: otpLoginResult.password_expiry_reminder,
      require_otp: otpLoginResult.require_otp,
      challenge_id: otpLoginResult.challenge_id,
      qr_code: otpLoginResult.qr_code,
      redirect_url: otpLoginResult.redirect_url,
    });
    setQrCodeUrl(otpLoginResult.qr_code || "");
    setAuthStep('otp-verification');
    setFormError("");
  };

  const loginAuthValidationMessages = {
    loadMethodsFailed: t('signin.loginAuth.validation.loadMethodsFailed'),
    timedOut: t('signin.loginAuth.validation.timedOut'),
    cancelled: t('signin.loginAuth.validation.cancelled'),
    failed: t('signin.loginAuth.validation.failed'),
    incompletePayload: t('signin.loginAuth.validation.incompletePayload'),
    syncFailed: t('signin.loginAuth.validation.syncFailed'),
    queryStatusFailed: t('signin.loginAuth.validation.queryStatusFailed'),
    startFailed: t('signin.loginAuth.validation.startFailed'),
    popupBlocked: t('signin.loginAuth.validation.popupBlocked'),
  };

  const loginAuthValidation = useLoginAuthValidation({
    enabled: authStep === 'login',
    callbackUrl: callbackUrl || '/',
    messages: loginAuthValidationMessages,
    onOtpRequired: applyOtpLoginResult,
    onSessionSync: async (loginResult) => {
      const success = await syncAuthenticatedSession({
        id: loginResult.id ? String(loginResult.id) : undefined,
        username: loginResult.username,
        display_name: loginResult.display_name,
        domain: loginResult.domain,
        token: loginResult.token,
        locale: loginResult.locale,
        timezone: loginResult.timezone,
        temporary_pwd: loginResult.temporary_pwd,
        enable_otp: loginResult.enable_otp,
        password_expiry_reminder: loginResult.password_expiry_reminder,
        redirect_url: loginResult.redirect_url,
      });

      if (!success) {
        setFormError(t('signin.errors.authenticationFailed'));
      }

      return success;
    },
  });

  const handleLoginSubmit = async (e: React.FormEvent, bindingId?: number) => {
    e.preventDefault();
    setIsLoading(true);
    setFormError("");

    const selectedBindingCredentials = bindingId
      ? (bindingCredentialMap[bindingId] || { username: "", password: "" })
      : { username, password };
    const requestUsername = selectedBindingCredentials.username;
    const requestPassword = selectedBindingCredentials.password;

    try {
      const response = await fetch('/api/proxy/core/api/login/', {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          binding_id: bindingId,
          username: requestUsername,
          password: requestPassword,
          domain: VALIDATION_MODE_DEFAULT_DOMAIN,
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

  const syncAuthenticatedSession = async (userData: LoginResponse, nextPassword?: string) => {
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
        password: nextPassword ?? password,
        skipValidation: 'true',
        userData: JSON.stringify(userDataForAuth),
        callbackUrl: callbackUrl || "/",
      }) as SignInResponse | undefined;

      if (result?.error) {
        console.error('SignIn error:', result.error);
        return false;
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

        finishAuthentication(targetUrl);
        return true;
      } else {
        console.error('SignIn failed with unknown error');
        return false;
      }
    } catch (error) {
      console.error("Failed to complete authentication:", error);
      return false;
    }
  };

  const completeAuthentication = async (userData: LoginResponse) => {
    const success = await syncAuthenticatedSession(userData);
    if (!success) {
      setFormError(t('signin.errors.authenticationFailed'));
      setIsLoading(false);
    }
  };

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
  const selectedBinding = loginAuthValidation.selectedBinding;
  const signinSurface = resolveSigninSurface(
    loginAuthValidation.bindingsLoadState,
    selectedBinding,
  );
  const bindingCredentials = selectedBinding
    ? (bindingCredentialMap[selectedBinding.id] || { username: "", password: "" })
    : { username: "", password: "" };
  const isValidationSelectionLocked = isBindingSelectionLocked({
    authStep,
    viewState: loginAuthValidation.viewState,
  });
  const showBindingsSelector = shouldShowBindingsSelector({
    authStep,
    bindingsLoadState: loginAuthValidation.bindingsLoadState,
    bindingsCount: loginAuthValidation.bindings.length,
  });
  const shouldShowValidationFormState = authStep === 'login';
  const validationInlineError = shouldShowValidationFormState
    ? resolveInlineValidationError(
      loginAuthValidation.bindingsLoadState,
      loginAuthValidation.viewState,
      loginAuthValidation.errorMessage,
    )
    : '';

  const builtinContent = (
    <BuiltinSigninContent
      mode={mode}
      username={username}
      password={password}
      isLoading={isLoading}
      usernameLabel={t('signin.form.username')}
      usernamePlaceholder={t('signin.form.usernamePlaceholder')}
      passwordLabel={t('signin.form.password')}
      passwordPlaceholder={t('signin.form.passwordPlaceholder')}
      submitText={t('signin.form.signIn')}
      loadingText={t('signin.form.signingIn')}
      onUsernameChange={setUsername}
      onPasswordChange={setPassword}
      onSubmit={handleLoginSubmit}
    />
  );

  const bindingPasswordContent = selectedBinding ? (
    <BuiltinSigninContent
      mode={mode}
      username={bindingCredentials.username}
      password={bindingCredentials.password}
      isLoading={isLoading}
      {...getBindingPasswordCopy(selectedBinding, t)}
      fieldIdPrefix={`binding-${selectedBinding.id}`}
      onUsernameChange={(value) => {
        setBindingCredentialMap((current) => ({
          ...current,
          [selectedBinding.id]: {
            username: value,
            password: current[selectedBinding.id]?.password || "",
          },
        }));
      }}
      onPasswordChange={(value) => {
        setBindingCredentialMap((current) => ({
          ...current,
          [selectedBinding.id]: {
            username: current[selectedBinding.id]?.username || "",
            password: value,
          },
        }));
      }}
      onSubmit={(event) => {
        void handleLoginSubmit(event, selectedBinding.id);
      }}
    />
  ) : null;

  const bindingContent = (
    <LoginAuthBindingContent
      mode={mode}
      bindingLoadState={loginAuthValidation.bindingsLoadState}
      selectedBinding={selectedBinding}
      viewState={loginAuthValidation.viewState}
      activeBindingName={loginAuthValidation.activeBindingName}
      errorMessage={loginAuthValidation.errorMessage}
      onRetryBindings={() => {
        void loginAuthValidation.reloadBindings();
      }}
      onContinueThirdParty={() => {
        void loginAuthValidation.startSelectedBindingLogin();
      }}
    />
  );

  const bindingsSelector = showBindingsSelector ? (
    <LoginAuthValidationPanel
      bindings={loginAuthValidation.bindings}
      selectedBindingId={loginAuthValidation.selectedBindingId}
      isSelectionLocked={isValidationSelectionLocked}
      onSelectBinding={loginAuthValidation.selectBinding}
    />
  ) : null;

  // SigninClient owns the shared authentication content area.
  // In page mode it wraps that content with the page shell; in modal mode
  // the modal shell above is rendered by auth.tsx.
  const sharedContent = (
    <div>
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

      {validationInlineError && (
        <div className={`mb-6 rounded border text-red-700 ${isModalMode ? 'px-3 py-2.5 text-[12px]' : 'border-l-4 border-red-500 bg-red-50 p-4'}`} style={isModalMode ? { borderColor: isDarkTheme ? 'rgba(239, 68, 68, 0.35)' : '#F5D4D4', background: isDarkTheme ? 'rgba(127, 29, 29, 0.18)' : '#FFF7F7' } : undefined}>
          <p className="font-medium">{validationInlineError}</p>
        </div>
      )}

      {authStep === 'login' && (
        <SigninContentShell
          mode={mode}
          mainContent={
            signinSurface === 'builtin-password'
              ? builtinContent
              : signinSurface === 'binding-password'
                ? bindingPasswordContent
                : bindingContent
          }
          methodsContent={bindingsSelector}
          methodsTitle={t('signin.loginAuth.methodsTitle')}
        />
      )}
      {authStep === 'reset-password' && renderPasswordResetForm()}
      {authStep === 'otp-verification' && renderOtpVerificationForm()}
    </div>
  );

  if (mode === 'modal') {
    return <div className="mx-auto w-full py-1" style={{ maxWidth: 388 }}>{sharedContent}</div>;
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
          <div className="w-full max-w-md">
            <div className="mb-10 text-center">
              <div className="mb-6 flex justify-center">
                <img src={logoUrl} alt="Logo" className="h-14 w-auto object-contain" />
              </div>
              <h2 className="text-3xl font-bold text-(--color-text-1)">{t('signin.pageTitle.login')}</h2>
              <p className="mt-2 text-(--color-text-3)">{t('signin.pageDescription.login')}</p>
            </div>
            {sharedContent}
          </div>
        </div>
      </div>
    </div>
  );
}
