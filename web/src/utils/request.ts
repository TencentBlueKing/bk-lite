import axios, { AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { useEffect, useCallback, useState } from 'react';
import { useAuth } from '@/context/auth';
import { message } from 'antd';
import { useSession } from 'next-auth/react';
import {
  createSessionExpiredRequestError,
  emitSessionExpired,
  isSessionExpiredState,
  SESSION_EXPIRED_REQUEST_ERROR,
} from '@/utils/sessionExpiry';
import { forceLogoutAndRedirect } from '@/utils/forceLogout';

const apiClient = axios.create({
  baseURL: '/api/proxy',
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Module-level token ref — updated by useApiClient via setToken()
const tokenRef: { current: string | null } = { current: null };

const setToken = (token: string | null) => {
  tokenRef.current = token;
};

const handleResponse = (response: AxiosResponse) => {
  const { result, message: msg, data } = response.data;
  if (!result) {
    throw new Error(msg);
  }
  return data;
};

// Register interceptors once at module level
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    if (isSessionExpiredState()) {
      return Promise.reject(createSessionExpiredRequestError());
    }

    if (!tokenRef.current) {
      return Promise.reject(new Error('No token available'));
    }

    config.headers.Authorization = `Bearer ${tokenRef.current}`;
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error) => {
    if (error.response) {
      const { status } = error.response;
      const messageText = error.response?.data?.message;
      if (status === 460) {
        void forceLogoutAndRedirect();
        return Promise.reject(error);
      } else if (status === 401) {
        emitSessionExpired({ reason: 'api-session-expired', status });
        return Promise.reject(error);
      } else if ([400, 403].includes(status)) {
        message.error(messageText);
        return Promise.reject(new Error(messageText));
      } else if (status === 500) {
        message.error(messageText);
        return Promise.reject(new Error(messageText || 'Internal Server Error'));
      }
    }
    return Promise.reject(error);
  }
);

export const isSilentRequestError = (error: unknown) => {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    return error.code === 'ECONNABORTED' || status === 401 || status === 460;
  }

  return error instanceof Error && [
    'No token available',
    SESSION_EXPIRED_REQUEST_ERROR,
  ].includes(error.message);
};

const useApiClient = () => {
  const authContext = useAuth();
  const { data: session } = useSession();
  const token = (session?.user as any)?.token || authContext?.token || null;
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setToken(token);
    if (token) {
      setIsLoading(false);
    }
  }, [token]);

  const get = useCallback(async <T = any>(url: string, config?: AxiosRequestConfig): Promise<T> => {
    const response = await apiClient.get<T>(url, config);
    return config?.responseType === 'blob' ? response.data : handleResponse(response);
  }, []);

  const post = useCallback(async <T = any>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> => {
    try {
      const response = await apiClient.post<T>(url, data, config);
      if (config?.responseType === 'blob') {
        return response.data;
      }
      return handleResponse(response);
    } catch (error) {
      throw error;
    }
  }, []);

  const put = useCallback(async <T = any>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> => {
    try {
      const response = await apiClient.put<T>(url, data, config);
      if (config?.responseType === 'blob') {
        return response.data;
      }
      return handleResponse(response);
    } catch (error) {
      throw error;
    }
  }, []);

  const del = useCallback(async <T = any>(url: string, config?: AxiosRequestConfig): Promise<T> => {
    try {
      const response = await apiClient.delete<T>(url, config);
      if (config?.responseType === 'blob') {
        return response.data;
      }
      return handleResponse(response);
    } catch (error) {
      throw error;
    }
  }, []);

  const patch = useCallback(async <T = any>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> => {
    try {
      const response = await apiClient.patch<T>(url, data, config);
      if (config?.responseType === 'blob') {
        return response.data;
      }
      return handleResponse(response);
    } catch (error) {
      throw error;
    }
  }, []);

  return { get, post, put, del, patch, isLoading };
};

export default useApiClient;
