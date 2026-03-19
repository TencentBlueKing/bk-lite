import axios, { AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { useEffect, useCallback, useState, useRef } from 'react';
import { useAuth } from '@/context/auth';
import { message } from 'antd';
import { signIn, signOut, useSession } from 'next-auth/react';
import { useTranslation } from '@/utils/i18n';

const apiClient = axios.create({
  baseURL: '/api/proxy',
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 全局 token 引用，供 interceptor 使用
let globalTokenRef: { current: string | null } = { current: null };
let interceptorsRegistered = false;

// 在模块级别注册 interceptor（只执行一次）
const setupInterceptors = () => {
  if (interceptorsRegistered) return;
  interceptorsRegistered = true;

  apiClient.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      if (globalTokenRef.current) {
        config.headers.Authorization = `Bearer ${globalTokenRef.current}`;
      }
      return config;
    },
    (error) => Promise.reject(error)
  );

  apiClient.interceptors.response.use(
    (response: AxiosResponse) => response,
    (error) => {
      if (error.response) {
        const { status } = error.response;
        if (status === 401) {
          signOut({ redirect: false }).then(() => {
            if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/auth/')) {
              signIn();
            }
          });
        }
      }
      return Promise.reject(error);
    }
  );
};

// 初始化 interceptors
setupInterceptors();

const handleResponse = (response: AxiosResponse, onError?: () => void) => {
  const { result, message: msg, data } = response.data;
  if (!result) {
    if (msg) {
      message.error(msg);
    }
    if (onError) {
      onError();
    }
    throw new Error(msg);
  }
  return data;
};

const useApiClient = () => {
  const { t } = useTranslation();
  const authContext = useAuth();
  const { data: session } = useSession();
  const token = (session?.user as any)?.token || authContext?.token || null;
  const isCheckingAuthRef = useRef(authContext?.isCheckingAuth ?? true);
  const isAuthenticatedRef = useRef(authContext?.isAuthenticated ?? false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    globalTokenRef.current = token;
    isCheckingAuthRef.current = authContext?.isCheckingAuth ?? true;
    isAuthenticatedRef.current = authContext?.isAuthenticated ?? false;
    setIsLoading(Boolean(authContext?.isCheckingAuth) || (Boolean(authContext?.isAuthenticated) && !token));
  }, [authContext?.isAuthenticated, authContext?.isCheckingAuth, token]);

  const waitForAuthReady = useCallback(async () => {
    if (globalTokenRef.current) {
      return globalTokenRef.current;
    }

    const startedAt = Date.now();

    while (isCheckingAuthRef.current && Date.now() - startedAt < 10000) {
      await new Promise((resolve) => setTimeout(resolve, 100));

      if (globalTokenRef.current) {
        return globalTokenRef.current;
      }
    }

    if (globalTokenRef.current) {
      return globalTokenRef.current;
    }

    const currentToken = (session?.user as any)?.token || authContext?.token || null;
    if (currentToken) {
      globalTokenRef.current = currentToken;
      return currentToken;
    }

    if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/auth/') && !isAuthenticatedRef.current) {
      signIn();
    }

    throw new Error('No token available');
  }, [session, authContext?.token]);

  const get = useCallback(async <T = any>(url: string, config?: AxiosRequestConfig, onError?: () => void): Promise<T> => {
    try {
      await waitForAuthReady();
      const response = await apiClient.get<T>(url, config);
      if (config?.responseType === 'blob') {
        return response.data;
      }
      return handleResponse(response, onError);
    } catch (error) {
      throw error;
    }
  }, [waitForAuthReady]);

  const post = useCallback(async <T = any>(url: string, data?: unknown, config?: AxiosRequestConfig, onError?: () => void): Promise<T> => {
    try {
      await waitForAuthReady();
      const response = await apiClient.post<T>(url, data, config);
      return handleResponse(response, onError);
    } catch (error) {
      throw error;
    }
  }, [waitForAuthReady]);

  const put = useCallback(async <T = any>(url: string, data?: unknown, config?: AxiosRequestConfig, onError?: () => void): Promise<T> => {
    try {
      await waitForAuthReady();
      const response = await apiClient.put<T>(url, data, config);
      return handleResponse(response, onError);
    } catch (error) {
      throw error;
    }
  }, [waitForAuthReady]);

  const del = useCallback(async <T = any>(url: string, config?: AxiosRequestConfig, onError?: () => void): Promise<T> => {
    try {
      await waitForAuthReady();
      const response = await apiClient.delete<T>(url, config);
      return handleResponse(response, onError);
    } catch (error) {
      throw error;
    }
  }, [waitForAuthReady]);

  const patch = useCallback(async <T = any>(url: string, data?: unknown, config?: AxiosRequestConfig, onError?: () => void): Promise<T> => {
    try {
      await waitForAuthReady();
      const response = await apiClient.patch<T>(url, data, config);
      return handleResponse(response, onError);
    } catch (error) {
      throw error;
    }
  }, [waitForAuthReady]);

  return { get, post, put, del, patch, isLoading };
};

export default useApiClient;
