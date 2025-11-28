'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import useApiClient from '@/utils/request';
import Spin from '@/components/spin';
import useNodeApi from '@/app/node-manager/api/useNodeApi';

interface NodeStateEnum {
  [key: string]: any;
}

interface CommonContextType {
  nodeStateEnum: NodeStateEnum;
}

const CommonContext = createContext<CommonContextType | null>(null);

const CommonContextProvider = ({ children }: { children: React.ReactNode }) => {
  const [nodeStateEnum, setNodeStateEnum] = useState<NodeStateEnum>({});
  const [pageLoading, setPageLoading] = useState(false);
  const { getNodeStateEnum } = useNodeApi();
  const { isLoading } = useApiClient();

  useEffect(() => {
    if (isLoading) return;
    fetchNodeStateEnum();
  }, [isLoading]);

  const fetchNodeStateEnum = async () => {
    setPageLoading(true);
    try {
      const responseData = await getNodeStateEnum();
      setNodeStateEnum(responseData || {});
    } finally {
      setPageLoading(false);
    }
  };

  return pageLoading ? (
    <Spin />
  ) : (
    <CommonContext.Provider value={{ nodeStateEnum }}>
      {children}
    </CommonContext.Provider>
  );
};

export const useCommon = () => useContext(CommonContext);

export default CommonContextProvider;
