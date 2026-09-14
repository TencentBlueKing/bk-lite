'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import useApiClient from '@/utils/request';
import useNodeApi from '@/app/node-manager/api/useNodeApi';

interface NodeStateEnum {
  [key: string]: any;
}

interface CommonContextType {
  nodeStateEnum: NodeStateEnum;
  /** 公共枚举后台加载中；列表页可先渲染再等枚举补齐 */
  commonLoading: boolean;
}

const CommonContext = createContext<CommonContextType | null>(null);

const CommonContextProvider = ({ children }: { children: React.ReactNode }) => {
  const [nodeStateEnum, setNodeStateEnum] = useState<NodeStateEnum>({});
  const [commonLoading, setCommonLoading] = useState(false);
  const { getNodeStateEnum } = useNodeApi();
  const { isLoading } = useApiClient();

  useEffect(() => {
    if (isLoading) return;
    fetchNodeStateEnum();
  }, [isLoading]);

  const fetchNodeStateEnum = async () => {
    setCommonLoading(true);
    try {
      const responseData = await getNodeStateEnum();
      setNodeStateEnum(responseData || {});
    } finally {
      setCommonLoading(false);
    }
  };

  // 不再用全屏 Spin 挡住子路由：布局挂载时也不再整页 LOADING
  return (
    <CommonContext.Provider value={{ nodeStateEnum, commonLoading }}>
      {children}
    </CommonContext.Provider>
  );
};

export const useCommon = () => useContext(CommonContext);

export default CommonContextProvider;
