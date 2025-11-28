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
  const token = session?.user?.token || authContext?.token || null;
  const tokenRef = useRef(token);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    tokenRef.current = token;
    if (token) {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    const requestInterceptor = apiClient.interceptors.request.use(
      (config: InternalAxiosRequestConfig) => {
        if (!tokenRef.current) {
          signIn();
          return Promise.reject(new Error('No token available'));
        }
        config.headers.Authorization = `Bearer ${tokenRef.current}`;
        return config;
      },
      (error) => {
        return Promise.reject(error);
      }
    );

    const responseInterceptor = apiClient.interceptors.response.use(
      (response: AxiosResponse) => response,
      (error) => {
        if (error.response) {
          const { status } = error.response;
          const messageText = error.response?.data?.message;
          if (status === 401) {
            signOut({ redirect: false }).then(() => {
              signIn();
            });
          } else if ([400, 403].includes(status)) {
            message.error(messageText);
            return Promise.reject(new Error(messageText));
          } else if (status === 500) {
            message.error(messageText);
            return Promise.reject(new Error(t('common.serverError')));
          }
        }
        return Promise.reject(error);
      }
    );

    return () => {
      apiClient.interceptors.request.eject(requestInterceptor);
      apiClient.interceptors.response.eject(responseInterceptor);
    };
  }, []);

  const get = useCallback(async <T = any>(url: string, config?: AxiosRequestConfig, onError?: () => void): Promise<T> => {
    try {
      const response = await apiClient.get<T>(url, config);
      return handleResponse(response, onError);
    } catch (error) {
      throw error;
    }
  }, []);

  const post = useCallback(async <T = any>(url: string, data?: unknown, config?: AxiosRequestConfig, onError?: () => void): Promise<T> => {
    try {
      const response = await apiClient.post<T>(url, data, config);
      return handleResponse(response, onError);
    } catch (error) {
      throw error;
    }
  }, []);

  const put = useCallback(async <T = any>(url: string, data?: unknown, config?: AxiosRequestConfig, onError?: () => void): Promise<T> => {
    try {
      const response = await apiClient.put<T>(url, data, config);
      return handleResponse(response, onError);
    } catch (error) {
      throw error;
    }
  }, []);

  const del = useCallback(async <T = any>(url: string, config?: AxiosRequestConfig, onError?: () => void): Promise<T> => {
    try {
      const response = await apiClient.delete<T>(url, config);
      return handleResponse(response, onError);
    } catch (error) {
      throw error;
    }
  }, []);

  const patch = useCallback(async <T = any>(url: string, data?: unknown, config?: AxiosRequestConfig, onError?: () => void): Promise<T> => {
    try {
      const response = await apiClient.patch<T>(url, data, config);
      return handleResponse(response, onError);
    } catch (error) {
      throw error;
    }
  }, []);

  return { get, post, put, del, patch, isLoading };
};

export default useApiClient;
