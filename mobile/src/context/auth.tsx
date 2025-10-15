'use client';
import React, { createContext, useContext, useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { SpinLoading } from 'antd-mobile';
import { AuthContextType } from '@/types/auth';

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
  const router = useRouter();
  const pathname = usePathname();

  // 定义公共路径，这些路径不需要认证
  const publicPaths = ['/login', '/register', '/forgot-password'];
  const isPublicPath = pathname && publicPaths.includes(pathname);

  useEffect(() => {
    // 初始化认证状态
    const initializeAuth = async () => {
      setIsInitializing(true);

      try {
        const localToken =
          typeof window !== 'undefined' ? localStorage.getItem('token') : null;

        setToken(localToken);
        setIsAuthenticated(!!localToken);

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

        if (!isPublicPath) {
          router.push('/login');
        }
      } finally {
        setIsInitializing(false);
      }
    };

    initializeAuth();
  }, [pathname, router, isPublicPath]);

  const login = (newToken: string) => {
    setToken(newToken);
    setIsAuthenticated(true);
    localStorage.setItem('token', newToken);
    router.push('/conversations');
  };

  const logout = async () => {
    setIsLoading(true);
    try {
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
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export default AuthProvider;
