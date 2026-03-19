import React, { createContext, useContext, useState, useEffect, useCallback, useRef, ReactNode } from 'react';
import useApiClient from '@/utils/request';
import { ClientData, AppConfigItem } from '@/types/index';

interface ClientDataContextType {
  clientData: ClientData[];
  appConfigList: AppConfigItem[];
  loading: boolean;
  appConfigLoading: boolean;
  getAll: () => Promise<ClientData[]>;
  reset: () => void;
  refresh: () => Promise<ClientData[]>;
  refreshAppConfig: () => Promise<AppConfigItem[]>;
}

const ClientDataContext = createContext<ClientDataContextType | undefined>(undefined);
const APP_ORDER = [
  'opspilot',
  'ops-console',
  'system-manager',
  'cmdb',
  'monitor',
  'log',
  'node',
  'alarm',
  'itsm',
  'ops-analysis',
  'mlops',
  'lab'
];

const sortClientData = (data: ClientData[]): ClientData[] => {
  if (data.length <= 1) {
    return data;
  }
  return [...data].sort((a, b) => {
    const indexA = APP_ORDER.indexOf(a.name);
    const indexB = APP_ORDER.indexOf(b.name);

    if (indexA !== -1 && indexB !== -1) {
      return indexA - indexB;
    }
    if (indexA !== -1) {
      return -1;
    }
    if (indexB !== -1) {
      return 1;
    }
    return 0;
  });
};

export const ClientProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { get, isLoading: apiLoading } = useApiClient();
  const [clientData, setClientData] = useState<ClientData[]>([]);
  const [appConfigList, setAppConfigList] = useState<AppConfigItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [appConfigLoading, setAppConfigLoading] = useState(true);
  const initializedRef = useRef(false);
  const appConfigInitializedRef = useRef(false);


  const initialize = useCallback(async () => {
    if (initializedRef.current) {
      return;
    }

    if (apiLoading) {
      return;
    }

    try {
      setLoading(true);
      const data = await get('/core/api/get_client/');
      if (data) {
        setClientData(sortClientData(data));
      }
      initializedRef.current = true;
    } catch (err) {
      console.error('Failed to fetch client data:', err);
    } finally {
      setLoading(false);
    }
  }, [get, apiLoading]);

  // 获取用户配置的应用列表
  const fetchAppConfig = useCallback(async () => {
    try {
      setAppConfigLoading(true);
      const data = await get('/console_mgmt/user_app_sets/current_user_apps/');
      if (data) {
        const sortedData = data.sort((a: AppConfigItem, b: AppConfigItem) => a.index - b.index);
        setAppConfigList(sortedData);
      }
      return data || [];
    } catch (err) {
      console.error('Failed to fetch app config:', err);
      return [];
    } finally {
      setAppConfigLoading(false);
    }
  }, [get]);

  // 初始化用户应用配置
  const initializeAppConfig = useCallback(async () => {
    if (appConfigInitializedRef.current) {
      return;
    }

    if (apiLoading) {
      return;
    }

    await fetchAppConfig();
    appConfigInitializedRef.current = true;
  }, [apiLoading, fetchAppConfig]);

  useEffect(() => {
    initialize();
  }, [initialize]);

  useEffect(() => {
    initializeAppConfig();
  }, [initializeAppConfig]);

  const getAll = useCallback(async () => {
    if (loading || apiLoading) {
      await initialize();
    }
    return [...clientData];
  }, [initialize, loading, apiLoading, clientData]);

  const refresh = useCallback(async () => {
    try {
      const data = await get('/core/api/get_client/');
      if (data) {
        setClientData(sortClientData(data));
      }
      return data || [];
    } catch (err) {
      console.error('Failed to refresh client data:', err);
      return [];
    }
  }, [get]);

  const refreshAppConfig = useCallback(async () => {
    return await fetchAppConfig();
  }, [fetchAppConfig]);

  const reset = useCallback(() => {
    setClientData([]);
    setAppConfigList([]);
    setLoading(true);
    setAppConfigLoading(true);
    initializedRef.current = false;
    appConfigInitializedRef.current = false;
  }, []);

  return (
    <ClientDataContext.Provider
      value={{ clientData, appConfigList, loading, appConfigLoading, getAll, reset, refresh, refreshAppConfig }}
    >
      {children}
    </ClientDataContext.Provider>
  );
};

export const useClientData = () => {
  const context = useContext(ClientDataContext);
  if (context === undefined) {
    throw new Error('useClientData must be used within a ClientProvider');
  }
  return context;
};
