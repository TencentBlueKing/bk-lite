import React, { createContext, useContext, useState, useEffect, useCallback, useRef, ReactNode } from 'react';
import useApiClient from '@/utils/request';
import { ClientData } from '@/types/index';

interface ClientDataContextType {
  clientData: ClientData[];
  myClientData: ClientData[];
  loading: boolean;
  getAll: () => Promise<ClientData[]>;
  reset: () => void;
}

const ClientDataContext = createContext<ClientDataContextType | undefined>(undefined);

export const ClientProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { get, isLoading: apiLoading } = useApiClient();
  const [clientData, setClientData] = useState<ClientData[]>([]);
  const [myClientData, setMyClientData] = useState<ClientData[]>([]);
  const [loading, setLoading] = useState(true);
  const initializedRef = useRef(false);

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
        setClientData(data);
      }
      const myClientData = await get('/core/api/get_my_client/', {
        params: {
          client_id: process.env.NEXT_PUBLIC_CLIENT_ID || ''
        }
      });
      if (myClientData) {
        setMyClientData(myClientData);
      }
      initializedRef.current = true;
    } catch (err) {
      console.error('Failed to fetch client data:', err);
    } finally {
      setLoading(false);
    }
  }, [get, apiLoading]);

  useEffect(() => {
    initialize();
  }, [initialize]);

  const getAll = useCallback(async () => {
    if (loading || apiLoading) {
      await initialize();
    }
    return [...clientData];
  }, [initialize, clientData, loading, apiLoading]);

  const reset = useCallback(() => {
    setClientData([]);
    setMyClientData([]);
    setLoading(true);
    initializedRef.current = false;
  }, []);

  return (
    <ClientDataContext.Provider
      value={{ clientData, myClientData, loading, getAll, reset }}
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
