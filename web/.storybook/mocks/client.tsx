'use client';

import React, { createContext, useContext } from 'react';
import type { AppConfigItem, ClientData } from '@/types/index';

interface ClientContextValue {
  clientData: ClientData[];
  appConfigList: AppConfigItem[];
  loading: boolean;
  appConfigLoading: boolean;
  getAll: () => Promise<ClientData[]>;
  reset: () => void;
  refresh: () => Promise<ClientData[]>;
  refreshAppConfig: () => Promise<AppConfigItem[]>;
}

const defaultClientData = [
  {
    id: 'system-manager',
    name: 'system-manager',
    display_name: 'System Manager',
    description: 'System manager application',
    url: '/system-manager',
  },
  {
    id: 'monitor',
    name: 'monitor',
    display_name: 'Monitor',
    description: 'Monitor application',
    url: '/monitor',
  },
  {
    id: 'cmdb',
    name: 'cmdb',
    display_name: 'CMDB',
    description: 'CMDB application',
    url: '/cmdb',
  },
  {
    id: 'ops-console',
    name: 'ops-console',
    display_name: 'Ops Console',
    description: 'Ops console application',
    url: '/ops-console',
  },
] satisfies ClientData[];

const ClientContext = createContext<ClientContextValue | undefined>(undefined);

interface ClientProviderProps {
  children: React.ReactNode;
  clientData?: ClientData[];
}

const createContextValue = (clientData: ClientData[]): ClientContextValue => ({
  clientData,
  appConfigList: [],
  loading: false,
  appConfigLoading: false,
  getAll: async () => clientData,
  reset: () => {},
  refresh: async () => clientData,
  refreshAppConfig: async () => [],
});

export const ClientProvider: React.FC<ClientProviderProps> = ({ children, clientData = defaultClientData }) => (
  <ClientContext.Provider value={createContextValue(clientData)}>
    {children}
  </ClientContext.Provider>
);

export const useClientData = () => {
  const context = useContext(ClientContext);
  if (context === undefined) {
    return {
      clientData: defaultClientData,
      appConfigList: [],
      loading: false,
      appConfigLoading: false,
      getAll: async () => defaultClientData,
      reset: () => {},
      refresh: async () => defaultClientData,
      refreshAppConfig: async () => [],
    };
  }
  return context;
};

export default ClientProvider;
