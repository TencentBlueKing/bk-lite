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
import { useAuth } from '@/context/auth';
import { getDomainList } from '@/api/auth';
import { AuthStep } from '@/types/auth';
import { useTranslation } from '@/utils/i18n';
import { withBasePath } from '@/utils/basePath';
import {
  isBuiltinLoginBinding,
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
import type { PublicLoginBinding } from '@/auth/im-login/types';
import styles from './page.module.css';

const INPUT_STYLE = {
  '--font-size': '16px',
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
  const { login, isInitializing } = useAuth();
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
  const retryTimerRef = React.useRef<NodeJS.Timeout | null>(null);

  const selectedBinding = resolveSelectedMobileBinding(bindings, selectedBindingId);
  const showMethodSelector = authStep === 'login' && bindings.length > 1;
  const isPasswordMethod = !selectedBinding || isBuiltinLoginBinding(selectedBinding);
  const busy = isLoading || isInitializing || startingExternal;

  useEffect(() => {
    const notice = consumeLoginNotice(window.sessionStorage);
    if (notice) {
      const presentation = presentationForLoginNotice(notice.reason);
      if (presentation.type === 'otp') {
        setAuthStep('otp-verification');
      } else if (presentation.type === 'password-reset') {
        setAuthStep('reset-password');
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
      const result = await login({ username, password, domain });
      if (result.status === 'invalid-credentials') {
        Toast.show({ content: result.message || t('auth.loginFailed'), icon: 'fail' });
        setPassword('');
        return;
      }
      if (result.status === 'password-reset-required') {
        setAuthStep('reset-password');
        return;
      }
      if (result.status === 'otp-required') {
        setAuthStep('otp-verification');
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

  const renderPasswordResetForm = () => (
    <div className={styles.statePanel}>
      <div className={styles.stateIcon} style={{ background: '#ffedd5' }}>
        <LockOutline fontSize={36} className="text-orange-600" />
      </div>
      <h3 className={styles.stateTitle}>{t('login.passwordResetRequired')}</h3>
      <p className={styles.stateHint}>{t('login.passwordResetHint')}</p>
      <Button color="primary" fill="outline" onClick={() => setAuthStep('login')} className="w-full h-11" style={{ fontSize: '16px' }}>
        {t('login.backToLogin')}
      </Button>
    </div>
  );

  const renderOtpVerificationForm = () => (
    <div className={styles.statePanel}>
      <div className={styles.stateIcon} style={{ background: '#dbeafe' }}>
        <LockOutline fontSize={36} className="text-blue-600" />
      </div>
      <h3 className={styles.stateTitle}>{t('login.twoFactorAuth')}</h3>
      <p className={styles.stateHint}>{t('login.twoFactorHint')}</p>
      <Button color="primary" fill="outline" onClick={() => setAuthStep('login')} className="w-full h-11" style={{ fontSize: '16px' }}>
        {t('login.backToLogin')}
      </Button>
    </div>
  );

  const renderDomainField = () => (
    <div className={styles.field}>
      <label className={styles.label}>{t('login.domain')}</label>
      {loadingDomains ? (
        <div className={styles.picker} style={{ justifyContent: 'center', gap: 8 }}>
          <SpinLoading color="primary" />
          <span style={{ color: '#6b7280', fontSize: 16 }}>{t('login.loadingDomains')}</span>
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
      {renderDomainField()}
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
        disabled={busy || !domain}
        className={LOGIN_ACTION_BUTTON_CLASS}
        style={loginActionButtonStyle(busy || !domain)}
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

  const pageTitle =
    authStep === 'reset-password'
      ? t('login.resetPassword')
      : authStep === 'otp-verification'
        ? t('login.verifyIdentity')
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
            <Button fill="outline" className="w-full h-11" onClick={() => setShowDomainSelector(false)} style={{ fontSize: '16px' }}>
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      </Mask>
    </div>
  );
}
