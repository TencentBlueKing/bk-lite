'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import { useSession, signIn } from 'next-auth/react';
import { useRouter, usePathname } from 'next/navigation';
import { Spin } from 'antd';
import { useLocale } from '@/context/locale';
import { saveAuthToken } from '@/utils/crossDomainAuth';

interface AuthContextType {
  token: string | null;
  isAuthenticated: boolean;
  isCheckingAuth: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { data: session, status } = useSession();
  const [token, setToken] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isCheckingAuth, setIsCheckingAuth] = useState<boolean>(true);
  const [hasCheckedExistingAuth, setHasCheckedExistingAuth] = useState<boolean>(false);
  const [isAutoSigningIn, setIsAutoSigningIn] = useState<boolean>(false);
  const [isCheckingExistingAuth, setIsCheckingExistingAuth] = useState<boolean>(false);
  const router = useRouter();
  const pathname = usePathname();
  const { setLocale } = useLocale();

  const authPaths = ['/auth/signin', '/auth/signout', '/auth/callback'];
  const isSessionValid = session && session.user && (session.user.id || session.user.username);

  // Check existing authentication using get_bk_settings API
  const checkExistingAuthentication = async () => {
    try {
      console.log('Checking existing authentication...');
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
          console.log('Found existing authentication, auto-signing in...', userData);
          
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
          
          console.log('Auto SignIn result:', result);
          
          if (result?.ok) {
            console.log('Auto SignIn successful');
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
      if (hasCheckedExistingAuth || (pathname && authPaths.includes(pathname))) {
        setIsCheckingAuth(false);
        return;
      }

      console.log('Performing initial auth check, status:', status);
      setHasCheckedExistingAuth(true);
      
      // Always check for existing authentication first, regardless of current session status
      // This ensures we don't miss existing auth when session loads quickly
      const hasExistingAuth = await checkExistingAuthentication();
      
      if (!hasExistingAuth) {
        console.log('No existing auth found, checking current session status:', status);
        // Only stop checking if we're sure there's no existing auth AND session is loaded
        if (status !== 'loading') {
          setIsCheckingAuth(false);
        }
      }
      // If existing auth found, let the session effect handle the rest
    };

    performInitialAuthCheck();
  }, [pathname, hasCheckedExistingAuth]);

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
    if (pathname && authPaths.includes(pathname)) {
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
        console.log('No valid session, redirecting to signin');
        router.push('/auth/signin');
      }
      return;
    }

    if (isSessionValid) {
      setToken(session.user?.token || session.user?.id || null);
      setIsAuthenticated(true);
      setIsCheckingAuth(false);
      const userLocale = session.user?.locale || 'en';
      const savedLocale = localStorage.getItem('locale') || 'en';
      if (userLocale !== savedLocale) {
        setLocale(userLocale);
      }
      localStorage.setItem('locale', userLocale);
    }
  }, [status, session, pathname, setLocale, router, isAutoSigningIn, hasCheckedExistingAuth, isCheckingExistingAuth]); // 添加 isCheckingExistingAuth 依赖

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
    </AuthContext.Provider>
  );
};

export default AuthProvider;
