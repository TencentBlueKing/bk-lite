'use client';

import React, { useState, useEffect } from 'react';
import Image from 'next/image';
import { useAuth } from '@/context/auth';
import { Input, Button, SpinLoading, Mask, Toast } from 'antd-mobile';
import { AuthStep } from '@/types/auth';
import { getDomainList, authLogin } from '@/api/auth';
import { useTranslation } from '@/utils/i18n';
import {
  EyeInvisibleOutline,
  EyeOutline,
  LockOutline,
  UserOutline,
  GlobalOutline,
  ExclamationTriangleOutline
} from 'antd-mobile-icons';

export default function LoginPage() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [domain, setDomain] = useState('');
  const [domainList, setDomainList] = useState<string[]>([]);
  const [loadingDomains, setLoadingDomains] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [authStep, setAuthStep] = useState<AuthStep>('login');
  const [showPassword, setShowPassword] = useState(false);
  const [showDomainSelector, setShowDomainSelector] = useState(false);
  const retryTimerRef = React.useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    fetchDomainList();

    return () => {
      // 组件卸载时清理定时器
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
    };
  }, []);

  const fetchDomainList = async () => {
    // 开始新的请求前，先清除可能存在的重试定时器
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
          setDomain(responseData.data[0]);
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

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      const responseData = await authLogin({
        username,
        password,
        domain,
      });

      if (!responseData.result) {
        const errorMessage = responseData.message || t('auth.loginFailed');
        Toast.show({ content: errorMessage, icon: 'fail' });
        setUsername('');
        setPassword('');
        setIsLoading(false);
        return;
      }

      const userData = responseData.data;
      if (userData.temporary_pwd) {
        setAuthStep('reset-password');
        setIsLoading(false);
        return;
      }

      if (userData.enable_otp) {
        setAuthStep('otp-verification');
        setIsLoading(false);
        return;
      }

      if (userData.token) {
        await login(userData.token, userData);
      }

      if (userData.redirect_url) {
        window.location.href = userData.redirect_url;
      }
    } catch (error) {
      console.error('Login error:', error);
      Toast.show({ content: t('login.systemError'), icon: 'fail' });
      setIsLoading(false);
    }
  };

  const renderPasswordResetForm = () => (
    <div className="text-center space-y-4">
      <div className="w-16 h-16 bg-orange-100 rounded-full flex items-center justify-center mx-auto mb-3">
        <LockOutline fontSize={36} className="text-orange-600" />
      </div>
      <h3 className="text-lg font-semibold text-gray-900">
        {t('login.passwordResetRequired')}
      </h3>
      <p className="text-base text-gray-600">
        {t('login.passwordResetHint')}
      </p>
      <Button
        color="primary"
        fill="outline"
        onClick={() => setAuthStep('login')}
        className="w-full h-11"
        style={{ fontSize: '16px' }}
      >
        {t('login.backToLogin')}
      </Button>
    </div>
  );

  const renderOtpVerificationForm = () => (
    <div className="text-center space-y-4">
      <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-3">
        <LockOutline fontSize={36} className="text-blue-600" />
      </div>
      <h3 className="text-lg font-semibold text-gray-900">
        {t('login.twoFactorAuth')}
      </h3>
      <p className="text-base text-gray-600">
        {t('login.twoFactorHint')}
      </p>
      <Button
        color="primary"
        fill="outline"
        onClick={() => setAuthStep('login')}
        className="w-full h-11"
        style={{ fontSize: '16px' }}
      >
        {t('login.backToLogin')}
      </Button>
    </div>
  );

  return (
    <div className="min-h-full bg-gradient-to-br from-blue-50 via-indigo-50 to-blue-100 flex flex-col justify-center">
      <div className="w-full max-w-sm mx-auto px-6 py-8">
        {/* Logo 和标题区域 */}
        <div className="text-center mb-6">
          <div className="flex justify-center mb-2">
            <Image
              src="/logo-site.png"
              alt="WeOps Logo"
              width={68}
              height={68}
              className="w-17 h-17 object-contain"
            />
          </div>
          <h1 className="text-2xl font-bold text-gray-900 mb-1">
            {authStep === 'login' && t('login.signIn')}
            {authStep === 'reset-password' && t('login.resetPassword')}
            {authStep === 'otp-verification' && t('login.verifyIdentity')}
          </h1>
        </div>

        {/* 表单容器 */}
        <div className="bg-white/95 backdrop-blur-sm rounded-xl shadow-lg p-5 border border-white/30">

          {authStep === 'login' && (
            <form onSubmit={handleLoginSubmit} className="space-y-4">
              {/* 域选择 */}
              <div className="space-y-1.5">
                <label className="text-base font-medium text-gray-500">
                  {t('login.domain')}
                </label>
                {loadingDomains ? (
                  <div className="flex items-center justify-center h-11 bg-gray-50 rounded-lg border border-gray-200">
                    <SpinLoading color="primary" />
                    <span className="ml-2 text-gray-600 text-base">
                      {t('login.loadingDomains')}
                    </span>
                  </div>
                ) : (
                  <div
                    className="flex items-center justify-between w-full h-11 px-3 bg-gray-50 rounded-lg border border-gray-100 cursor-pointer hover:bg-gray-100 transition-colors"
                    onClick={() => setShowDomainSelector(true)}
                  >
                    <div className="flex items-center space-x-2.5">
                      <GlobalOutline className="text-gray-400 text-base" />
                      <span className="text-gray-900 text-base">
                        {domain || t('login.selectDomain')}
                      </span>
                    </div>
                    <div className="text-gray-400 text-lg">›</div>
                  </div>
                )}
                {!loadingDomains && domainList.length === 0 && (
                  <div className="text-amber-600 text-sm bg-amber-50 border border-amber-200 px-2.5 py-1.5 rounded-lg flex items-center space-x-2">
                    <ExclamationTriangleOutline className="text-lg" />
                    <span>{t('login.noDomainsAvailable')}</span>
                  </div>
                )}
              </div>

              {/* 用户名输入 */}
              <div className="space-y-1.5">
                <label className="text-base font-medium text-gray-500">
                  {t('auth.username')}
                </label>
                <div className="relative">
                  <UserOutline className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 z-10 text-base" />
                  <Input
                    className='login-input'
                    placeholder={t('login.enterUsername')}
                    value={username}
                    onChange={setUsername}
                    disabled={isLoading}
                    style={{
                      '--font-size': '16px',
                      '--color': '#111827',
                      '--placeholder-color': '#9ca3af',
                      height: '44px',
                      backgroundColor: '#f9fafb',
                      borderRadius: '0.5rem',
                      border: '1px solid #e5e7eb',
                      paddingLeft: '2.5rem',
                    }}
                  />
                </div>
              </div>

              {/* 密码输入 */}
              <div className="space-y-1.5">
                <label className="text-base font-medium text-gray-500">
                  {t('auth.password')}
                </label>
                <div className="relative">
                  <LockOutline className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 z-10 text-base" />
                  <Input
                    className='login-input'
                    placeholder={t('login.enterPassword')}
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={setPassword}
                    disabled={isLoading}
                    style={{
                      '--font-size': '16px',
                      '--color': '#111827',
                      '--placeholder-color': '#9ca3af',
                      height: '44px',
                      backgroundColor: '#f9fafb',
                      borderRadius: '0.5rem',
                      border: '1px solid #e5e7eb',
                      paddingLeft: '2.5rem',
                      paddingRight: '2.5rem',
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 z-10"
                  >
                    {showPassword ? (
                      <EyeOutline className="text-base" />
                    ) : (
                      <EyeInvisibleOutline className="text-base" />
                    )}
                  </button>
                </div>
              </div>

              {/* 登录按钮 */}
              <Button
                type="submit"
                loading={isLoading}
                disabled={isLoading || !domain}
                className="w-full h-11 rounded-lg shadow-sm mt-5"
                style={{
                  backgroundColor:
                    isLoading || !domain ? '#e5e7eb' : '#2563eb',
                  color: '#ffffff',
                  borderRadius: '0.5rem',
                  fontSize: '16px',
                  fontWeight: '500',
                }}
              >
                {isLoading ? t('login.signingIn') : t('login.signIn')}
              </Button>
            </form>
          )}

          {authStep === 'reset-password' && renderPasswordResetForm()}
          {authStep === 'otp-verification' && renderOtpVerificationForm()}
        </div>
      </div>

      {/* 域选择弹窗 */}
      <Mask
        visible={showDomainSelector}
        onMaskClick={() => setShowDomainSelector(false)}
      >
        <div className="fixed inset-x-4 top-1/2 transform -translate-y-1/2 bg-white rounded-xl shadow-2xl max-w-sm mx-auto">
          <div className="p-6">
            <div className="text-center mb-4">
              <h3 className="text-lg font-semibold text-gray-900">
                {t('login.selectDomain')}
              </h3>
            </div>
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {domainList.map((d) => (
                <div
                  key={d}
                  className={`flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors mb-4 ${domain === d
                    ? 'bg-blue-50 border-2 border-blue-200'
                    : 'bg-gray-50 hover:bg-gray-100 border border-gray-200'
                    }`}
                  onClick={() => {
                    setDomain(d);
                    setShowDomainSelector(false);
                  }}
                >
                  <span
                    className={`text-base ${domain === d
                      ? 'text-blue-700 font-medium'
                      : 'text-gray-900'
                      }`}
                  >
                    {d}
                  </span>
                  {domain === d && (
                    <div className="w-2 h-2 bg-blue-600 rounded-full"></div>
                  )}
                </div>
              ))}
            </div>
            <Button
              fill="outline"
              className="w-full h-11"
              onClick={() => setShowDomainSelector(false)}
              style={{ fontSize: '16px' }}
            >
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      </Mask>
    </div>
  );
}
