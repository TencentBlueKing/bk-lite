'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import axios from 'axios';
import { useSession, signIn } from 'next-auth/react';
import type { Session } from 'next-auth';
import { useRouter, usePathname } from 'next/navigation';
import { Spin, message } from 'antd';
import { useLocale } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';
import { saveAuthToken } from '@/utils/crossDomainAuth';
import SigninClient from '@/app/(core)/auth/signin/SigninClient';
import { AUTH_POPUP_SUCCESS_MESSAGE } from '@/utils/authRedirect';
import {
  createSessionExpiredRequestError,
  emitSessionExpired,
  isAuthPath,
  isSessionExpiredState,
  resetSessionExpiredState,
  SESSION_EXPIRED_EVENT,
  shouldTriggerSessionExpiry,
} from '@/utils/sessionExpiry';

// Type assertion helper for session
type ExtendedSession = Session & {
  user: {
    id: string;
    username?: string;
    token?: string;
    locale?: string;
    name?: string | null;
    email?: string | null;
    image?: string | null;
  }
};

interface AuthContextType {
  token: string | null;
  isAuthenticated: boolean;
  isCheckingAuth: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

const modalSigninErrors: Record<string | 'default', string> = {
  default: 'Unable to sign in.',
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { data: session, status } = useSession();
  const extendedSession = session as unknown as ExtendedSession | null;
  const [token, setToken] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isCheckingAuth, setIsCheckingAuth] = useState<boolean>(true);
  const [hasCheckedExistingAuth, setHasCheckedExistingAuth] = useState<boolean>(false);
  const [isAutoSigningIn, setIsAutoSigningIn] = useState<boolean>(false);
  const [isCheckingExistingAuth, setIsCheckingExistingAuth] = useState<boolean>(false);
  const [sessionExpiredOpen, setSessionExpiredOpen] = useState<boolean>(false);
  const router = useRouter();
  const pathname = usePathname();
  const { setLocale } = useLocale();
  const { t } = useTranslation();

  const authPaths = ['/auth/signin', '/auth/signout', '/auth/callback'];
  const isCurrentAuthPath = isAuthPath(pathname);
  const isSessionValid = extendedSession && extendedSession.user && (extendedSession.user.id || extendedSession.user.username);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const nativeFetch = window.fetch.bind(window);

    window.fetch = async (input, init) => {
      if (shouldTriggerSessionExpiry(input) && isSessionExpiredState()) {
        throw createSessionExpiredRequestError();
      }

      const response = await nativeFetch(input, init);

      if (response.status === 401 && shouldTriggerSessionExpiry(input)) {
        emitSessionExpired({ reason: 'global-fetch-session-expired', status: 401 });
      }

      return response;
    };

    const axiosRequestInterceptor = axios.interceptors.request.use((config) => {
      if (shouldTriggerSessionExpiry(config.url) && isSessionExpiredState()) {
        return Promise.reject(createSessionExpiredRequestError());
      }

      return config;
    });

    const axiosResponseInterceptor = axios.interceptors.response.use(
      (response) => {
        if (response.status === 401 && shouldTriggerSessionExpiry(response.config.url)) {
          emitSessionExpired({ reason: 'global-axios-session-expired', status: 401 });
        }

        return response;
      },
      (error) => {
        if (axios.isAxiosError(error) && error.response?.status === 401 && shouldTriggerSessionExpiry(error.config?.url)) {
          emitSessionExpired({ reason: 'global-axios-session-expired', status: 401 });
        }

        return Promise.reject(error);
      }
    );

    return () => {
      window.fetch = nativeFetch;
      axios.interceptors.request.eject(axiosRequestInterceptor);
      axios.interceptors.response.eject(axiosResponseInterceptor);
    };
  }, []);

  // Check existing authentication using get_bk_settings API
  const checkExistingAuthentication = async () => {
    try {
      setIsCheckingExistingAuth(true);

      const response = await fetch('/api/proxy/core/api/get_bk_settings/', {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-cache, no-store, must-revalidate",
          "Pragma": "no-cache",
        },
        credentials: 'include',
      });

      const responseData = await response.json();

      if (response.ok && responseData.result && responseData.data) {
        // Try different paths to find user data
        const userData = responseData.data.user;

        // Check if we have valid user information
        if (userData && (userData.username || userData.id)) {
          setIsAutoSigningIn(true);

          const userDataForAuth = {
            id: userData.id,
            username: userData.username,
            token: userData.token,
            locale: userData.locale || 'en',
            temporary_pwd: userData.temporary_pwd || false,
            enable_otp: userData.enable_otp || false,
            qrcode: userData.qrcode || false,
          };

          // Save auth token if available
          if (userData.token) {
            saveAuthToken({
              id: userDataForAuth.id,
              username: userDataForAuth.username || '',
              token: userData.token,
              locale: userDataForAuth.locale,
              temporary_pwd: userDataForAuth.temporary_pwd,
              enable_otp: userDataForAuth.enable_otp,
              qrcode: userDataForAuth.qrcode,
            });
          }

          // Auto sign in with existing authentication
          const result = await signIn("credentials", {
            redirect: false,
            username: userDataForAuth.username,
            password: '',
            skipValidation: 'true',
            userData: JSON.stringify(userDataForAuth),
          });

          if (result?.ok) {
            setTimeout(() => {
              setIsAutoSigningIn(false);
            }, 1000);
            return true;
          } else if (result?.error) {
            console.error('Auto SignIn error:', result.error);
            setIsAutoSigningIn(false);
          }
        } else {
          console.log('No valid user information in response');
        }
      } else {
        console.log('No existing authentication found or API call failed');
      }
    } catch (error) {
      console.error("Error checking existing authentication:", error);
    } finally {
      setIsCheckingExistingAuth(false);
    }

    setIsAutoSigningIn(false);
    return false;
  };

  // Initial authentication check on app start
  useEffect(() => {
    const performInitialAuthCheck = async () => {
      // Only check once and skip for auth pages
      if (hasCheckedExistingAuth || isCurrentAuthPath) {
        setIsCheckingAuth(false);
        return;
      }

      setHasCheckedExistingAuth(true);

      // Always check for existing authentication first, regardless of current session status
      // This ensures we don't miss existing auth when session loads quickly
      const hasExistingAuth = await checkExistingAuthentication();

      if (!hasExistingAuth) {
        // Only stop checking if we're sure there's no existing auth AND session is loaded
        if (status !== 'loading') {
          setIsCheckingAuth(false);
        }
      }
      // If existing auth found, let the session effect handle the rest
    };

    performInitialAuthCheck();
  }, [hasCheckedExistingAuth, isCurrentAuthPath, pathname]);

  useEffect(() => {
    const handleSessionExpired = () => {
      if (isCurrentAuthPath) {
        return;
      }

      setSessionExpiredOpen(true);
      setIsCheckingAuth(false);
    };

    window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired as EventListener);

    return () => {
      window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired as EventListener);
    };
  }, [isCurrentAuthPath]);

  useEffect(() => {
    const handleAuthPopupMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) {
        return;
      }

      if (event.data?.type !== AUTH_POPUP_SUCCESS_MESSAGE) {
        return;
      }

      handleReloginSuccess();
    };

    window.addEventListener('message', handleAuthPopupMessage);

    return () => {
      window.removeEventListener('message', handleAuthPopupMessage);
    };
  }, []);

  // Process session changes
  useEffect(() => {
    // If session is loading or auto signing in, do nothing
    if (status === 'loading' || isAutoSigningIn) {
      return;
    }

    // If we haven't checked existing auth yet, wait
    if (!hasCheckedExistingAuth) {
      return;
    }

    // If the existing authentication check is in progress (API request pending), wait for it to complete
    if (isCheckingExistingAuth) {
      return;
    }

    // If current path is auth-related page, allow access
    if (isCurrentAuthPath) {
      setIsCheckingAuth(false);
      return;
    }

    // If no valid session, redirect to login page
    if (status === 'unauthenticated' || !isSessionValid) {
      setToken(null);
      setIsAuthenticated(false);
      setIsCheckingAuth(false);

      // Only redirect if:
      // 1. Not currently auto signing in
      // 2. Not on auth pages
      // 3. Have completed the initial auth check
      // 4. Not currently checking existing auth (新增条件)
      if (pathname && !authPaths.includes(pathname) && !isAutoSigningIn && hasCheckedExistingAuth && !isCheckingExistingAuth) {
        if (sessionExpiredOpen) {
          setIsCheckingAuth(false);
        } else {
          router.push('/auth/signin');
        }
      }
      return;
    }

    if (isSessionValid) {
      setToken(extendedSession.user?.token || extendedSession.user?.id || null);
      setIsAuthenticated(true);
      setIsCheckingAuth(false);
      const userLocale = extendedSession.user?.locale || 'en';
      const savedLocale = localStorage.getItem('locale') || 'en';
      if (userLocale !== savedLocale) {
        setLocale(userLocale);
      }
      localStorage.setItem('locale', userLocale);
    }
  }, [status, session, pathname, setLocale, router, isAutoSigningIn, hasCheckedExistingAuth, isCheckingExistingAuth, isCurrentAuthPath, sessionExpiredOpen]);

  const handleReloginSuccess = () => {
    setSessionExpiredOpen(false);
    resetSessionExpiredState();
    message.success(t('common.reloginSuccess'));
    window.location.reload();
  };

  // Show loading state until authentication state is determined
  if ((status === 'loading' || isCheckingAuth || isAutoSigningIn || isCheckingExistingAuth) && pathname && !authPaths.includes(pathname)) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <Spin size="large" />
          <p className="mt-4 text-gray-600">
            {isAutoSigningIn ? 'Auto signing in...' :
            isCheckingExistingAuth ? 'Checking existing authentication...' :
            isCheckingAuth ? 'Checking Authentication...' : 'Loading...'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ token, isAuthenticated, isCheckingAuth }}>
      {children}
      {sessionExpiredOpen && !isCurrentAuthPath && (
        <div className="fixed inset-0 z-1200 flex items-center justify-center bg-black/35 px-4">
          <div className="w-full max-w-130 rounded-2xl border border-(--color-border-1) bg-(--color-bg-1) p-6 shadow-2xl">
            <div className="mb-6">
              <div className="mx-auto max-w-md text-center">
                <div className="text-[16px] font-semibold leading-none text-(--color-text-1)">
                  {t('common.sessionExpiredTitle')}
                </div>

                <div className="mx-auto mt-2 max-w-sm text-[12px] leading-5 text-(--color-text-3)">
                  {t('common.sessionExpiredDescription')}
                </div>

                <div className="mx-auto mt-3 h-px w-12 bg-linear-to-r from-transparent via-[#D9E2EC] to-transparent" />
              </div>
            </div>
            <SigninClient
              mode="modal"
              signinErrors={modalSigninErrors}
              onAuthenticated={handleReloginSuccess}
              showThirdPartyLogin
            />
          </div>
        </div>
      )}
    </AuthContext.Provider>
  );
};

export default AuthProvider;
