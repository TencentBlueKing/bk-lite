import { useContext } from 'react';

import { useOptionalClientData } from '@/context/client';
import { UserInfoContext } from '@/context/userInfo';

export const useDashboardModuleAccess = (
  useIdentityAppList: boolean,
  identityAuthorizedAppNames?: readonly string[] | null,
) => {
  const clientContext = useOptionalClientData();
  // 分享 / 订阅只用链接或执行身份的应用列表。列表还没到时保持未就绪，
  // 不能改读当前登录用户的 ClientProvider。
  if (useIdentityAppList) {
    const ready = Array.isArray(identityAuthorizedAppNames);
    return {
      authorizedAppNames: ready ? [...identityAuthorizedAppNames] : [],
      appAccessReady: ready,
    };
  }
  if (!clientContext) {
    throw new Error('useClientData must be used within a ClientProvider');
  }
  return {
    authorizedAppNames: clientContext.clientData
      .map((item) => item.name)
      .filter((name) => Boolean(name)),
    appAccessReady: !clientContext.loading,
  };
};

export const useDashboardSelectedGroup = (renderMode: boolean) => {
  const userInfo = useContext(UserInfoContext);
  if (!renderMode && userInfo === undefined) {
    throw new Error('useUserInfoContext must be used within a UserInfoProvider');
  }
  return userInfo?.selectedGroup ?? null;
};
