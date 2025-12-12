'use client';
import React, { createContext, useContext, useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { SpinLoading } from 'antd-mobile';
import { AuthContextType } from '@/types/auth';
import { LoginUserInfo } from '@/types/user';
import { useLocale } from '@/context/locale';
import {
  initSecureStorage,
  saveToken,
  saveUserInfo,
  getToken,
  getUserInfoFromStorage,
  clearAuthData,
} from '@/utils/secureStorage';

const AuthContext = createContext<AuthContextType | null>(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [token, setToken] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isInitializing, setIsInitializing] = useState<boolean>(true);
  const [userInfo, setUserInfo] = useState<LoginUserInfo | null>(null);
  const router = useRouter();
  const pathname = usePathname();
  const { setLocale } = useLocale();

  // 定义公共路径，这些路径不需要认证
  const publicPaths = ['/login', '/register', '/forgot-password'];
  const isPublicPath = pathname && publicPaths.includes(pathname);

  useEffect(() => {
    // 初始化认证状态
    const initializeAuth = async () => {
      setIsInitializing(true);

      try {
        // 初始化安全存储并加载数据到内存缓存
        await initSecureStorage();

        // 从安全存储获取 token 和用户信息
        const localToken = await getToken();
        const localUserInfo = await getUserInfoFromStorage();

        setToken(localToken);
        setIsAuthenticated(!!localToken);

        // 恢复用户信息
        if (localUserInfo) {
          setUserInfo(localUserInfo);
        }

        // 如果是初始化阶段，等待一小段时间确保路由稳定
        await new Promise((resolve) => setTimeout(resolve, 100));

        // 如果当前路径是公共路径，允许访问
        if (isPublicPath) {
          setIsInitializing(false);
          return;
        }

        // 如果没有token且不是公共路径，跳转到登录页
        if (!localToken && pathname && !isPublicPath) {
          console.log('未认证用户访问受保护页面，跳转登录页:', pathname);
          router.push('/login');
        }
      } catch (error) {
        console.error('认证初始化错误:', error);
        setToken(null);
        setIsAuthenticated(false);
        setUserInfo(null);

        if (!isPublicPath) {
          router.push('/login');
        }
      } finally {
        setIsInitializing(false);
      }
    };

    initializeAuth();
  }, [pathname, router, isPublicPath]);

  const login = async (newToken: string, newUserInfo: LoginUserInfo) => {
    setToken(newToken);
    setIsAuthenticated(true);
    setUserInfo(newUserInfo);

    // 使用安全存储保存认证数据
    await saveToken(newToken);
    await saveUserInfo(newUserInfo);

    // 同步用户的语言设置
    if (newUserInfo.locale) {
      setLocale(newUserInfo.locale);
    }

    // 尝试获取用户最后打开的对话页
    let targetUrl = '/conversation'; // 默认跳转
    try {
      const LAST_CONVERSATION_KEY = 'bk_lite_last_conversation';
      const lastConversationStr = localStorage.getItem(LAST_CONVERSATION_KEY);
      if (lastConversationStr) {
        const lastConversation = JSON.parse(lastConversationStr);
        if (lastConversation.botId) {
          targetUrl = `/conversation?bot_id=${lastConversation.botId}`;
          if (lastConversation.sessionId) {
            targetUrl += `&session_id=${lastConversation.sessionId}`;
          }
        }
      }
    } catch (e) {
      console.warn('get last conversation failed:', e);
    }

    router.push(targetUrl);
  };

  // 更新用户信息
  const updateUserInfo = async (updates: Partial<LoginUserInfo>) => {
    if (!userInfo) return;

    const updatedUserInfo = { ...userInfo, ...updates };
    setUserInfo(updatedUserInfo);

    // 同步更新安全存储
    await saveUserInfo(updatedUserInfo);
  };

  const logout = async () => {
    setIsLoading(true);
    try {
      // 使用安全存储清除认证数据
      await clearAuthData();

      // 同时清理可能残留的 localStorage 和 sessionStorage
      if (typeof window !== 'undefined') {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        localStorage.removeItem('refreshToken');
        localStorage.removeItem('userInfo');
        sessionStorage.clear();
      }

      // 更新认证状态
      setToken(null);
      setIsAuthenticated(false);
      setUserInfo(null);

      console.log('用户已成功退出登录');

      // 跳转到登录页面
      router.push('/login');
    } catch (error) {
      console.error('退出登录过程中发生错误:', error);

      // 即使出错也要清理本地状态并跳转
      if (typeof window !== 'undefined') {
        localStorage.clear();
        sessionStorage.clear();
      }
      setToken(null);
      setIsAuthenticated(false);
      setUserInfo(null);
      router.push('/login');
    } finally {
      setIsLoading(false);
    }
  };

  // 如果正在初始化且不是公共路径，显示加载状态
  if (isInitializing && !isPublicPath) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-[var(--color-background-body)] gap-3">
        <SpinLoading color="primary" style={{ '--size': '32px' }} />
      </div>
    );
  }

  // 如果用户未认证且访问受保护页面，显示加载状态（等待跳转）
  if (!isAuthenticated && !isPublicPath && !isInitializing) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-[var(--color-background-body)] gap-3">
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
