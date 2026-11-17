'use client';

import React, { useEffect, useState } from 'react';
import Image from 'next/image';
import { Button, Input, Mask, SpinLoading, Toast } from 'antd-mobile';
import {
  EyeInvisibleOutline,
  EyeOutline,
  ExclamationTriangleOutline,
  GlobalOutline,
  LockOutline,
  UserOutline,
} from 'antd-mobile-icons';
import { useIntl } from 'react-intl';
import { useAuth } from '@/context/auth';
import { getDomainList, resetPassword, verifyOtpLogin } from '@/api/auth';
import { AuthStep } from '@/types/auth';
import { useTranslation } from '@/utils/i18n';
import { withBasePath } from '@/utils/basePath';
import {
  isBuiltinLoginBinding,
  isPasswordLoginBinding,
  resolveInitialMobileBindingId,
  resolveSelectedMobileBinding,
} from '@/auth/im-login/bindings';
import {
  loadMobileLoginBindings,
  startBrowserExternalLogin,
} from '@/auth/im-login/browser';
import { externalSignInMessageId } from '@/auth/im-login/external-sign-in-label';
import { LOGIN_ACTION_BUTTON_CLASS, loginActionButtonStyle } from '@/auth/im-login/login-button-style';
import { LoginMethodIcon } from '@/auth/im-login/login-method-icon';
import { LoginProviderIconSprite } from '@/auth/im-login/login-provider-icon-sprite';
import { consumeLoginNotice, presentationForLoginNotice } from '@/auth/im-login/notices';
import {
  clearPendingLogin,
  continuationOfLoginData,
  pendingForStorage,
  readPendingLogin,
  savePendingLogin,
} from '@/auth/im-login/pending-login';
import type { ExternalLoginResult, PublicLoginBinding } from '@/auth/im-login/types';
import styles from './page.module.css';

const AD_LOGIN_DOMAIN = 'domain.com';

function formatSetupKey(key: string) {
  return key.replace(/\s+/g, '').replace(/(.{4})(?=.)/g, '$1 ');
}

function copyText(value: string) {
  const input = document.createElement('textarea');
  input.value = value;
  input.setAttribute('readonly', '');
  input.style.position = 'fixed';
  input.style.top = '0';
  input.style.left = '0';
  input.style.opacity = '0';
  document.body.appendChild(input);
  input.focus();
  input.select();
  input.setSelectionRange(0, value.length);
  let copied = false;
  try {
    copied = document.execCommand('copy');
  } finally {
    document.body.removeChild(input);
  }
  if (!copied) {
    throw new Error('copy failed');
  }
}

async function copySetupKeyText(value: string) {
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      copyText(value);
      return;
    }
  }
  copyText(value);
}

function formatAppList(apps: string[], orWord: string, locale: string) {
  if (apps.length <= 1) return apps[0] ?? '';
  const last = apps[apps.length - 1];
  const rest = apps.slice(0, -1);
  if (locale.startsWith('zh')) return `${rest.join('、')} ${orWord} ${last}`;
  if (apps.length === 2) return `${apps[0]} ${orWord} ${last}`;
  return `${rest.join(', ')}, ${orWord} ${last}`;
}

const INPUT_STYLE = {
  '--font-size': 'var(--font-size-subtitle)',
  '--color': '#111827',
  '--placeholder-color': '#9ca3af',
  height: '46px',
  backgroundColor: '#f9fafb',
  borderRadius: '8px',
  border: '1px solid #e5e7eb',
  paddingLeft: '2.5rem',
} as React.CSSProperties;

export default function LoginPage() {
  const { t } = useTranslation();
  const intl = useIntl();
  const { login, completeLogin, isInitializing } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [domain, setDomain] = useState('');
  const [domainList, setDomainList] = useState<string[]>([]);
  const [loadingDomains, setLoadingDomains] = useState(true);
  const [bindings, setBindings] = useState<PublicLoginBinding[]>([]);
  const [loadingBindings, setLoadingBindings] = useState(true);
  const [selectedBindingId, setSelectedBindingId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [startingExternal, setStartingExternal] = useState(false);
  const [authStep, setAuthStep] = useState<AuthStep>('login');
  const [showPassword, setShowPassword] = useState(false);
  const [showDomainSelector, setShowDomainSelector] = useState(false);
  const [pendingLogin, setPendingLogin] = useState<ExternalLoginResult | null>(null);
  const [otpCode, setOtpCode] = useState('');
  const [showSetupKey, setShowSetupKey] = useState(false);
  const [showQr, setShowQr] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [stepError, setStepError] = useState('');
  const retryTimerRef = React.useRef<NodeJS.Timeout | null>(null);

  const selectedBinding = resolveSelectedMobileBinding(bindings, selectedBindingId);
  const showMethodSelector = authStep === 'login' && bindings.length > 1;
  const isPasswordMethod = !selectedBinding || isPasswordLoginBinding(selectedBinding);
  const isBuiltinMethod = !selectedBinding || isBuiltinLoginBinding(selectedBinding);
  const isAdMethod = Boolean(selectedBinding && isPasswordLoginBinding(selectedBinding) && !isBuiltinLoginBinding(selectedBinding));
  const busy = isLoading || isInitializing || startingExternal;

  useEffect(() => {
    const notice = consumeLoginNotice(window.sessionStorage);
    const pending = readPendingLogin(window.sessionStorage);
    const continuation = continuationOfLoginData(pending);
    if (continuation === 'otp' || continuation === 'reset') {
      setPendingLogin(pending);
      setAuthStep(continuation === 'otp' ? 'otp-verification' : 'reset-password');
    } else if (notice) {
      const presentation = presentationForLoginNotice(notice.reason);
      if (presentation.type === 'otp' || presentation.type === 'password-reset') {
        Toast.show({
          content: t('login.sessionFailed', undefined, { name: notice.name || t('login.thirdParty') }),
          icon: 'fail',
        });
      } else {
        const name = notice.name || t('login.thirdParty');
        Toast.show({
          content: t(presentation.messageKey, undefined, { name }),
          icon: 'fail',
        });
      }
    }
    fetchDomainList();
    return () => {
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    let active = true;
    setLoadingBindings(true);
    loadMobileLoginBindings()
      .then((items) => {
        if (!active) return;
        setBindings(items);
        setSelectedBindingId((current) => {
          if (current && items.some((item) => item.id === current)) return current;
          return resolveInitialMobileBindingId(items);
        });
      })
      .catch(() => {
        if (!active) return;
        setBindings([]);
        setSelectedBindingId(null);
      })
      .finally(() => {
        if (active) setLoadingBindings(false);
      });
    return () => {
      active = false;
    };
  }, [domain]);

  const fetchDomainList = async () => {
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    try {
      setLoadingDomains(true);
      const responseData = await getDomainList();
      if (responseData.result && Array.isArray(responseData.data)) {
        setDomainList(responseData.data);
        if (responseData.data.length > 0) {
          setDomain((current) => current || responseData.data[0]);
        }
      } else {
        setDomainList([]);
        retryTimerRef.current = setTimeout(() => {
          fetchDomainList();
        }, 5000);
      }
    } catch (error) {
      console.error('Failed to fetch domain list:', error);
      setDomainList([]);
      retryTimerRef.current = setTimeout(() => {
        fetchDomainList();
      }, 5000);
    } finally {
      setLoadingDomains(false);
    }
  };

  const methodLabel = (binding: PublicLoginBinding) => {
    if (isBuiltinLoginBinding(binding)) return t('login.passwordMethod');
    return binding.name;
  };

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isInitializing) return;
    setIsLoading(true);
    try {
      const result = await login({
        username,
        password,
        domain: isAdMethod ? AD_LOGIN_DOMAIN : domain,
        bindingId: isAdMethod ? selectedBinding?.id : undefined,
      });
      if (result.status === 'invalid-credentials') {
        Toast.show({ content: result.message || t('auth.loginFailed'), icon: 'fail' });
        setPassword('');
        return;
      }
      if (result.status === 'password-reset-required' || result.status === 'otp-required') {
        setPendingLogin(readPendingLogin(window.sessionStorage));
        setStepError('');
        setAuthStep(result.status === 'otp-required' ? 'otp-verification' : 'reset-password');
        return;
      }
      if (result.status === 'service-unavailable') {
        Toast.show({ content: t('login.serviceUnavailable'), icon: 'fail' });
      }
    } catch (error) {
      console.error('Login error:', error);
      Toast.show({ content: t('login.systemError'), icon: 'fail' });
    } finally {
      setIsLoading(false);
    }
  };

  const handleExternalLogin = async () => {
    if (!selectedBinding || isBuiltinLoginBinding(selectedBinding)) return;
    setStartingExternal(true);
    try {
      const started = await startBrowserExternalLogin(selectedBinding);
      if (!started) {
        Toast.show({
          content: t('login.externalUnavailable', undefined, { name: selectedBinding.name }),
          icon: 'fail',
        });
      }
    } catch {
      Toast.show({
        content: t('login.externalUnavailable', undefined, { name: selectedBinding.name }),
        icon: 'fail',
      });
    } finally {
      setStartingExternal(false);
    }
  };

  const returnToLogin = () => {
    clearPendingLogin(window.sessionStorage);
    setPendingLogin(null);
    setOtpCode('');
    setNewPassword('');
    setConfirmPassword('');
    setStepError('');
    setAuthStep('login');
  };

  const finishPending = async (next: ExternalLoginResult) => {
    const stored = pendingForStorage(next);
    const continuation = continuationOfLoginData(stored);
    if (continuation === 'otp' || continuation === 'reset') {
      savePendingLogin(window.sessionStorage, stored);
      setPendingLogin(stored);
      setStepError('');
      setAuthStep(continuation === 'otp' ? 'otp-verification' : 'reset-password');
      return;
    }
    const result = await completeLogin(next);
    if (result.status === 'success') return;
    setStepError(result.status === 'invalid-credentials'
      ? t('auth.loginFailed')
      : t('login.serviceUnavailable'));
  };

  const handleOtpSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!otpCode) {
      setStepError(t('login.otpRequired'));
      return;
    }
    if (!pendingLogin?.challenge_id) {
      setStepError(t('login.sessionFailed', undefined, { name: '' }));
      return;
    }
    setIsLoading(true);
    setStepError('');
    try {
      const response = await verifyOtpLogin({
        challenge_id: pendingLogin.challenge_id,
        otp_code: otpCode,
      });
      if (!response?.result || !response.data) {
        setStepError(response?.message || t('login.invalidOtp'));
        return;
      }
      await finishPending({
        ...pendingLogin,
        ...response.data,
        require_otp: false,
        challenge_id: undefined,
      });
    } catch {
      setStepError(t('login.serviceUnavailable'));
    } finally {
      setIsLoading(false);
    }
  };

  const handlePasswordReset = async (event: React.FormEvent) => {
    event.preventDefault();
    if (newPassword !== confirmPassword) {
      setStepError(t('login.passwordMismatch'));
      return;
    }
    if (newPassword.length < 8) {
      setStepError(t('login.passwordTooShort'));
      return;
    }
    if (!pendingLogin?.token) {
      setStepError(t('login.sessionFailed', undefined, { name: '' }));
      return;
    }
    setIsLoading(true);
    setStepError('');
    try {
      const response = await resetPassword(pendingLogin.token, newPassword);
      if (!response?.result) {
        setStepError(response?.message || t('login.passwordResetFailed'));
        return;
      }
      const rotatedToken = typeof response.data?.token === 'string' ? response.data.token : pendingLogin.token;
      await finishPending({
        ...pendingLogin,
        token: rotatedToken,
        temporary_pwd: false,
        require_otp: false,
        challenge_id: undefined,
      });
    } catch {
      setStepError(t('login.serviceUnavailable'));
    } finally {
      setIsLoading(false);
    }
  };

  const renderStepError = () => (
    stepError ? <p className={styles.stepError}>{stepError}</p> : null
  );

  const renderPasswordResetForm = () => (
    <form onSubmit={handlePasswordReset}>
      <p className={styles.stateHint}>{t('login.passwordResetDescription')}</p>
      <div className={styles.field}>
        <label className={styles.label}>{t('auth.username')}</label>
        <Input className={`${styles.stepInput} login-input`} value={pendingLogin?.username || username} disabled />
      </div>
      <div className={styles.field}>
        <label className={styles.label}>{t('login.newPassword')}</label>
        <Input
          className={`${styles.stepInput} login-input`}
          type="password"
          value={newPassword}
          onChange={setNewPassword}
          placeholder={t('login.newPasswordPlaceholder')}
          disabled={busy}
        />
      </div>
      <div className={styles.field}>
        <label className={styles.label}>{t('login.confirmPassword')}</label>
        <Input
          className={`${styles.stepInput} login-input`}
          type="password"
          value={confirmPassword}
          onChange={setConfirmPassword}
          placeholder={t('login.confirmPasswordPlaceholder')}
          disabled={busy}
        />
      </div>
      {renderStepError()}
      <div className={styles.stepActions}>
        <Button
          type="submit"
          loading={isLoading}
          disabled={busy}
          className={`w-full rounded-lg shadow-sm ${styles.stepButton}`}
          style={{ ...loginActionButtonStyle(busy), height: 40, fontSize: 'var(--font-size-body)' }}
        >
          {isLoading ? t('login.resettingPassword') : t('login.resetPasswordSubmit')}
        </Button>
        <Button
          color="primary"
          fill="outline"
          onClick={returnToLogin}
          className={`w-full ${styles.stepButton}`}
          style={{ height: 40, fontSize: 'var(--font-size-body)', borderRadius: 8 }}
        >
          {t('login.backToLogin')}
        </Button>
      </div>
    </form>
  );

  const renderOtpVerificationForm = () => {
    const apps = pendingLogin?.otp_recommended_apps ?? [];
    const isBinding = Boolean(pendingLogin?.qr_code || pendingLogin?.need_binding);
    const appList = formatAppList(apps, t('login.or'), intl.locale);
    const copySetupKey = async () => {
      const setupKey = pendingLogin?.otp_setup_key;
      if (!setupKey) return;
      try {
        await copySetupKeyText(setupKey.replace(/\s+/g, ''));
        Toast.show({ content: t('login.otpCopied') });
      } catch {
        Toast.show({ content: t('login.otpCopyFailed'), icon: 'fail' });
      }
    };
    const codeField = (placeholder: string, compact = false) => (
      <div className={compact ? styles.bindField : styles.field}>
        <Input
          className={`${styles.stepInput} ${styles.otpInput} login-input`}
          value={otpCode}
          onChange={(value) => setOtpCode(value.replace(/\D/g, '').slice(0, 6))}
          placeholder={placeholder}
          maxLength={6}
          disabled={busy}
        />
      </div>
    );
    return (
      <form onSubmit={handleOtpSubmit}>
        {isBinding ? (
          <div className={styles.bindSections}>
            <div>
            <h2 className={styles.sectionTitle}>{t('login.otpStepAdd')}</h2>
            <p className={styles.bindHint}>
              {apps.length > 0
                ? t('login.otpBindStepHintApps', undefined, { apps: appList })
                : t('login.otpBindStepHint')}
            </p>
            {pendingLogin?.qr_code ? (
              <div className={styles.modeSwitch} role="tablist">
                <button
                  type="button"
                  role="tab"
                  aria-selected={!showQr}
                  className={!showQr ? `${styles.modeOption} ${styles.modeOptionActive}` : styles.modeOption}
                  onClick={() => setShowQr(false)}
                >
                  {t('login.otpManualTitle')}
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={showQr}
                  className={showQr ? `${styles.modeOption} ${styles.modeOptionActive}` : styles.modeOption}
                  onClick={() => setShowQr(true)}
                >
                  {t('login.otpQrTitle')}
                </button>
              </div>
            ) : null}
            {showQr && pendingLogin?.qr_code ? (
              <div className={styles.qrPanel}>
                <div className={styles.qrFrame}>
                  <img
                    src={`data:image/png;base64,${pendingLogin.qr_code}`}
                    alt={t('login.otpQrAlt')}
                  />
                </div>
              </div>
            ) : pendingLogin?.otp_setup_key ? (
              <>
                <p className={styles.quietLabel}>{t('login.otpSetupKeyLabel')}</p>
                <div className={styles.keyBox}>
                  <p className={showSetupKey ? styles.setupKeyValue : styles.setupKeyMasked}>
                    {showSetupKey ? formatSetupKey(pendingLogin.otp_setup_key) : t('login.otpKeyHidden')}
                  </p>
                  <div className={styles.keyActions}>
                    <button
                      type="button"
                      className={styles.showKey}
                      aria-pressed={showSetupKey}
                      onClick={() => setShowSetupKey((visible) => !visible)}
                    >
                      {t(showSetupKey ? 'login.otpHideKey' : 'login.otpShowKey')}
                    </button>
                    <button type="button" className={styles.copyLink} onClick={() => void copySetupKey()}>
                      {t('login.otpCopyKey')}
                    </button>
                  </div>
                </div>
                <p className={styles.keyHint}>{t('login.otpKeepSecret')}</p>
              </>
            ) : null}
            </div>
            <div>
            <h2 className={styles.sectionTitle}>{t('login.otpStepVerify')}</h2>
            {codeField(t('login.otpPlaceholderBind'), true)}
            </div>
          </div>
        ) : (
          <>
            <p className={styles.stateHint}>{t('login.otpDescription')}</p>
            {codeField(t('login.otpPlaceholderBind'), true)}
          </>
        )}
        {renderStepError()}
        <div className={`${styles.stepActions} ${styles.bindActions}`}>
          <Button
            type="submit"
            loading={isLoading}
            disabled={busy}
            className={LOGIN_ACTION_BUTTON_CLASS}
            style={loginActionButtonStyle(busy)}
          >
            {isLoading ? t('login.verifyingOtp') : t(isBinding ? 'login.otpFinishBind' : 'login.verifyOtp')}
          </Button>
          <button type="button" className={styles.textAction} onClick={returnToLogin}>
            {t(isBinding ? 'login.otpLeaveBind' : 'login.backToLogin')}
          </button>
        </div>
        {isBinding ? null : <p className={styles.secretNote}>{t('login.otpResetHint')}</p>}
      </form>
    );
  };

  const renderDomainField = () => (
    <div className={styles.field}>
      <label className={styles.label}>{t('login.domain')}</label>
      {loadingDomains ? (
        <div className={styles.picker} style={{ justifyContent: 'center', gap: 8 }}>
          <SpinLoading color="primary" />
          <span style={{ color: '#6b7280', fontSize: 'var(--font-size-subtitle)' }}>{t('login.loadingDomains')}</span>
        </div>
      ) : (
        <div className={styles.picker} onClick={() => setShowDomainSelector(true)}>
          <div className={styles.pickerLeft}>
            <GlobalOutline className="text-gray-400 text-base" />
            <span className={styles.pickerText}>{domain || t('login.selectDomain')}</span>
          </div>
          <span className={styles.pickerChevron}>›</span>
        </div>
      )}
      {!loadingDomains && domainList.length === 0 && (
        <div className={styles.warn}>
          <ExclamationTriangleOutline className="text-lg" />
          <span>{t('login.noDomainsAvailable')}</span>
        </div>
      )}
    </div>
  );

  const renderPasswordContent = () => (
    <form onSubmit={handleLoginSubmit}>
      {isBuiltinMethod ? renderDomainField() : null}
      <div className={styles.field}>
        <label className={styles.label}>{t('auth.username')}</label>
        <div className={styles.control}>
          <UserOutline className={styles.controlIcon} />
          <Input
            className="login-input"
            placeholder={t('login.enterUsername')}
            value={username}
            onChange={setUsername}
            disabled={busy}
            style={INPUT_STYLE}
          />
        </div>
      </div>
      <div className={styles.field}>
        <label className={styles.label}>{t('auth.password')}</label>
        <div className={styles.control}>
          <LockOutline className={styles.controlIcon} />
          <Input
            className="login-input"
            placeholder={t('login.enterPassword')}
            type={showPassword ? 'text' : 'password'}
            value={password}
            onChange={setPassword}
            disabled={busy}
            style={{ ...INPUT_STYLE, paddingRight: '2.5rem' }}
          />
          <button type="button" onClick={() => setShowPassword(!showPassword)} className={styles.controlAction}>
            {showPassword ? <EyeOutline className="text-base" /> : <EyeInvisibleOutline className="text-base" />}
          </button>
        </div>
      </div>
      <Button
        type="submit"
        loading={isLoading}
        disabled={busy || (isBuiltinMethod && !domain)}
        className={LOGIN_ACTION_BUTTON_CLASS}
        style={loginActionButtonStyle(busy || (isBuiltinMethod && !domain))}
      >
        {isLoading ? t('login.signingIn') : t('login.signIn')}
      </Button>
    </form>
  );

  const renderExternalContent = () => {
    if (!selectedBinding) return null;
    const name = selectedBinding.name;
    return (
      <div>
        {renderDomainField()}
        <div className={styles.oauthCard}>
          <div className={styles.oauthIconWrap}>
            <LoginMethodIcon icon={selectedBinding.icon} size={28} />
          </div>
          <div className={styles.oauthTitle}>{t('login.externalTitle', undefined, { name })}</div>
          <div className={styles.oauthDesc}>{t('login.externalDescription', undefined, { name })}</div>
        </div>
        <Button
          loading={startingExternal}
          disabled={busy || !domain}
          className={LOGIN_ACTION_BUTTON_CLASS}
          style={loginActionButtonStyle(busy || !domain)}
          onClick={() => {
            void handleExternalLogin();
          }}
        >
          {t(externalSignInMessageId(name), undefined, { name })}
        </Button>
        <p className={styles.helper}>{t('login.externalHelperRedirect', undefined, { name })}</p>
      </div>
    );
  };

  const isOtpBinding = authStep === 'otp-verification' && Boolean(pendingLogin?.qr_code || pendingLogin?.need_binding);
  const bindAccountName = pendingLogin?.username || username;
  const pageTitle =
    authStep === 'reset-password'
      ? t('login.resetPassword')
      : authStep === 'otp-verification'
        ? t(isOtpBinding ? 'login.otpBindTitle' : 'login.verifyIdentity')
        : t('login.signIn');

  return (
    <div className={styles.page}>
      <LoginProviderIconSprite />
      <div className={styles.shell}>
        <div className={styles.brand}>
          <div className="flex justify-center">
            <Image
              src={withBasePath('/logo-site.png')}
              alt="WeOps Logo"
              width={68}
              height={68}
              className="w-17 h-17 object-contain"
            />
          </div>
          <h1 className={styles.title}>{pageTitle}</h1>
          {authStep === 'otp-verification' && bindAccountName ? <p className={styles.accountCaption}>{bindAccountName}</p> : null}
        </div>

        <div className={styles.card}>
          {authStep === 'login' && (
            <>
              {loadingBindings && bindings.length === 0 ? (
                <div className="flex items-center justify-center py-10">
                  <SpinLoading color="primary" />
                </div>
              ) : isPasswordMethod ? (
                renderPasswordContent()
              ) : (
                renderExternalContent()
              )}

              {showMethodSelector && (
                <div className={styles.methods}>
                  <div className={styles.methodsTitle}>{t('login.methodsTitle')}</div>
                  <div className={styles.methodRow}>
                    {bindings.map((binding) => {
                      const active = binding.id === selectedBinding?.id;
                      return (
                        <button
                          key={binding.id}
                          type="button"
                          className={`${styles.methodItem} ${active ? styles.methodItemActive : ''}`}
                          aria-pressed={active}
                          onClick={() => setSelectedBindingId(binding.id)}
                        >
                          <span className={styles.methodIcon}>
                            <LoginMethodIcon icon={binding.icon || (isBuiltinLoginBinding(binding) ? 'zhanghaomima' : undefined)} size={20} />
                          </span>
                          <span className={styles.methodName}>{methodLabel(binding)}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </>
          )}

          {authStep === 'reset-password' && renderPasswordResetForm()}
          {authStep === 'otp-verification' && renderOtpVerificationForm()}
        </div>
      </div>

      <Mask visible={showDomainSelector} onMaskClick={() => setShowDomainSelector(false)}>
        <div className="fixed inset-x-4 top-1/2 transform -translate-y-1/2 bg-white rounded-xl shadow-2xl max-w-sm mx-auto">
          <div className="p-6">
            <div className="text-center mb-4">
              <h3 className="text-lg font-semibold text-gray-900">{t('login.selectDomain')}</h3>
            </div>
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {domainList.map((item) => (
                <div
                  key={item}
                  className={`flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors mb-4 ${
                    domain === item
                      ? 'bg-blue-50 border-2 border-blue-200'
                      : 'bg-gray-50 hover:bg-gray-100 border border-gray-200'
                  }`}
                  onClick={() => {
                    setDomain(item);
                    setShowDomainSelector(false);
                  }}
                >
                  <span className={`text-base ${domain === item ? 'text-blue-700 font-medium' : 'text-gray-900'}`}>
                    {item}
                  </span>
                  {domain === item && <div className="w-2 h-2 bg-blue-600 rounded-full" />}
                </div>
              ))}
            </div>
            <Button fill="outline" className="w-full h-11" onClick={() => setShowDomainSelector(false)} style={{ fontSize: 'var(--font-size-subtitle)' }}>
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      </Mask>
    </div>
  );
}
