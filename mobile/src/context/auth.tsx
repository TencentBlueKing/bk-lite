'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { getSession, signIn, signOut } from 'next-auth/react';
import { Button, SpinLoading, Toast } from 'antd-mobile';
import {
  AuthContextType,
  AuthLoginCredentials,
  AuthLoginResult,
} from '@/types/auth';
import { LoginUserInfo } from '@/types/user';
import { useLocale } from '@/context/locale';
import {
  clearAuthData,
  getToken,
  getUserInfoFromStorage,
  initSecureStorage,
  saveToken,
  saveUserInfo,
} from '@/utils/secureStorage';
import { authLogin, authLogout, getLoginInfo } from '@/api/auth';
import {
  setRuntimeAuthToken,
  setUnauthorizedHandler,
  UnauthorizedRequestError,
} from '@/api/request';
import {
  clearRejectedH5Session,
  loginWithH5Session,
  logoutH5Session,
  restoreH5Session,
} from '@/auth/h5Auth';
import { clearCurrentTeamCookie, syncCurrentTeamCookie } from '@/utils/teamCookie';
import { isTauriApp } from '@/utils/tauriFetch';
import { useTranslation } from '@/utils/i18n';

const AuthContext = createContext<AuthContextType | null>(null);

class RejectedSessionError extends Error {
  constructor() {
    super('Backend rejected the authenticated session');
    this.name = 'RejectedSessionError';
  }
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
};

function normalizeUserInfo(
  token: string,
  data: Record<string, unknown>,
  baseUserInfo: LoginUserInfo | null,
): LoginUserInfo {
  return {
    ...(baseUserInfo || {}),
    ...data,
    id: Number(data.id ?? data.user_id ?? baseUserInfo?.id ?? 0),
    username: String(data.username ?? baseUserInfo?.username ?? ''),
    display_name: String(data.display_name ?? baseUserInfo?.display_name ?? ''),
    domain: String(data.domain ?? baseUserInfo?.domain ?? ''),
    locale: String(data.locale ?? baseUserInfo?.locale ?? 'zh-CN'),
    token,
    temporary_pwd: false,
    enable_otp: false,
    qrcode: false,
  };
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const [initializationError, setInitializationError] = useState(false);
  const [initializationAttempt, setInitializationAttempt] = useState(0);
  const [userInfo, setUserInfo] = useState<LoginUserInfo | null>(null);
  const router = useRouter();
  const pathname = usePathname();
  const { setLocale } = useLocale();
  const { t } = useTranslation();

  const publicPaths = ['/login', '/register', '/forgot-password'];
  const isPublicPath = Boolean(pathname && publicPaths.includes(pathname));

  const resetLocalState = useCallback(async () => {
    await clearAuthData();
    clearCurrentTeamCookie();
    setRuntimeAuthToken(isTauriApp() ? undefined : null);
    setToken(null);
    setIsAuthenticated(false);
    setUserInfo(null);
  }, []);

  const establishAuthenticatedState = useCallback(async (
    nextToken: string,
    baseUserInfo: LoginUserInfo | null,
    persistToken: boolean,
  ) => {
    setRuntimeAuthToken(persistToken ? undefined : nextToken);
    const response = await getLoginInfo();
    if (!response?.result || !response.data) {
      throw new RejectedSessionError();
    }

    const completeUserInfo = normalizeUserInfo(nextToken, response.data, baseUserInfo);
    if (persistToken) {
      await saveToken(nextToken);
    }
    await saveUserInfo(completeUserInfo);
    syncCurrentTeamCookie(completeUserInfo);

    setToken(nextToken);
    setIsAuthenticated(true);
    setUserInfo(completeUserInfo);
    if (completeUserInfo.locale) {
      setLocale(completeUserInfo.locale);
    }

    return completeUserInfo;
  }, [setLocale]);

  const navigateAfterLogin = useCallback(() => {
    let targetUrl = '/workbench';
    try {
      const lastConversationStr = localStorage.getItem('bk_lite_last_conversation');
      if (lastConversationStr) {
        const lastConversation = JSON.parse(lastConversationStr);
        if (lastConversation.botId) {
          targetUrl = `/conversation?bot_id=${lastConversation.botId}`;
          if (lastConversation.sessionId) {
            targetUrl += `&session_id=${lastConversation.sessionId}`;
          }
        }
      }
    } catch (error) {
      console.warn('get last conversation failed:', error);
    }
    router.replace(targetUrl);
  }, [router]);

  const clearH5Session = useCallback(async () => {
    const result = await logoutH5Session({
      federatedLogout: async () => {
        const response = await fetch('/api/auth/federated-logout', {
          method: 'POST',
          credentials: 'include',
        });
        return { ok: response.ok };
      },
      signOut: (options) => signOut(options),
    });
    return result.backendLogoutAccepted;
  }, []);

  const clearRejectedSession = useCallback(async () => {
    if (isTauriApp()) {
      await resetLocalState();
      return;
    }

    await clearRejectedH5Session({
      clearSession: clearH5Session,
      resetLocalState,
    });
  }, [clearH5Session, resetLocalState]);

  const handleUnauthorized = useCallback(async () => {
    if (!isTauriApp()) {
      await clearH5Session();
    }
    await resetLocalState();
    router.replace('/login');
  }, [clearH5Session, resetLocalState, router]);

  useEffect(() => {
    setUnauthorizedHandler(handleUnauthorized);
    return () => setUnauthorizedHandler(null);
  }, [handleUnauthorized]);

  useEffect(() => {
    let active = true;

    const initializeAuth = async () => {
      setIsInitializing(true);
      setInitializationError(false);

      try {
        await initSecureStorage();

        if (isTauriApp()) {
          setRuntimeAuthToken(undefined);
          const localToken = await getToken();
          const localUserInfo = await getUserInfoFromStorage();
          if (!localToken) {
            clearCurrentTeamCookie();
          } else {
            await establishAuthenticatedState(localToken, localUserInfo, true);
          }
          return;
        }

        await clearAuthData();
        setRuntimeAuthToken(null);
        const sessionToken = await restoreH5Session({
          getSession,
          clearSession: clearH5Session,
        });
        if (!sessionToken) {
          clearCurrentTeamCookie();
          return;
        }

        await establishAuthenticatedState(sessionToken, null, false);
      } catch (error) {
        if (error instanceof RejectedSessionError) {
          await clearRejectedSession();
        } else if (error instanceof UnauthorizedRequestError) {
          await resetLocalState();
        } else {
          console.error('认证初始化错误:', error);
          if (active) setInitializationError(true);
        }
      } finally {
        if (active) setIsInitializing(false);
      }
    };

    void initializeAuth();
    return () => {
      active = false;
    };
  }, [clearH5Session, clearRejectedSession, establishAuthenticatedState, initializationAttempt, resetLocalState]);

  useEffect(() => {
    if (isInitializing || initializationError) return;
    if (!isAuthenticated && !isPublicPath && pathname) {
      router.replace('/login');
    }
  }, [initializationError, isAuthenticated, isInitializing, isPublicPath, pathname, router]);

  const login = async (credentials: AuthLoginCredentials): Promise<AuthLoginResult> => {
    if (isInitializing) return { status: 'service-unavailable' };

    setIsLoading(true);
    try {
      if (!isTauriApp()) {
        const result = await loginWithH5Session(credentials, {
          signIn: (provider, options) => signIn(provider, options),
          getSession,
        });
        if (result.status !== 'success') {
          if (
            result.status === 'otp-required'
            || result.status === 'password-reset-required'
          ) {
            await clearH5Session();
          }
          return result;
        }

        await establishAuthenticatedState(result.token, null, false);
        navigateAfterLogin();
        return { status: 'success' };
      }

      const response = await authLogin(credentials);
      if (!response?.result || !response.data) {
        return {
          status: 'invalid-credentials',
          message: response?.message,
        };
      }

      const userData = response.data as LoginUserInfo & { require_otp?: boolean };
      if (userData.require_otp || userData.enable_otp) {
        return { status: 'otp-required' };
      }
      if (userData.temporary_pwd) {
        if (userData.token) await authLogout(userData.token).catch(() => undefined);
        return { status: 'password-reset-required' };
      }
      if (!userData.token) return { status: 'invalid-credentials' };

      await establishAuthenticatedState(userData.token, userData, true);
      navigateAfterLogin();
      return { status: 'success' };
    } catch (error) {
      console.error('Login error:', error);
      if (error instanceof RejectedSessionError) {
        await clearRejectedSession();
      }
      return { status: 'service-unavailable' };
    } finally {
      setIsLoading(false);
    }
  };

  const updateUserInfo = async (updates: Partial<LoginUserInfo>) => {
    if (!userInfo) return;
    const updatedUserInfo = { ...userInfo, ...updates };
    setUserInfo(updatedUserInfo);
    await saveUserInfo(updatedUserInfo);
    syncCurrentTeamCookie(updatedUserInfo);
  };

  const logout = async () => {
    setIsLoading(true);
    try {
      let backendLogoutAccepted = true;
      if (isTauriApp()) {
        if (token) await authLogout(token);
      } else {
        backendLogoutAccepted = await clearH5Session();
      }
      if (!backendLogoutAccepted) {
        Toast.show({ content: t('login.logoutIncomplete'), icon: 'fail' });
      }
    } catch (error) {
      console.error('退出登录过程中发生错误:', error);
      Toast.show({ content: t('login.logoutIncomplete'), icon: 'fail' });
    } finally {
      await resetLocalState();
      setIsLoading(false);
      router.replace('/login');
    }
  };

  if (initializationError && !isPublicPath) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-[var(--color-background-body)] px-6 text-center">
        <p className="text-sm text-[var(--color-text-secondary)]">
          {t('login.serviceUnavailable')}
        </p>
        <Button color="primary" onClick={() => setInitializationAttempt((value) => value + 1)}>
          {t('common.retry')}
        </Button>
      </div>
    );
  }

  if (isInitializing && !isPublicPath) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 bg-[var(--color-background-body)]">
        <SpinLoading color="primary" style={{ '--size': '32px' }} />
      </div>
    );
  }

  if (!isAuthenticated && !isPublicPath && !isInitializing) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 bg-[var(--color-background-body)]">
        <SpinLoading color="primary" style={{ '--size': '32px' }} />
      </div>
    );
  }

  return (
    <AuthContext.Provider
      value={{
        token,
        isAuthenticated,
        isLoading,
        isInitializing,
        userInfo,
        login,
        logout,
        updateUserInfo,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export default AuthProvider;
