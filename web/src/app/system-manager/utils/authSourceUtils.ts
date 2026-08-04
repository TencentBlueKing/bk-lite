import { AuthSource } from '@/app/system-manager/types/security';
import { getAuthSourceTypeMap } from '@/app/system-manager/constants/authSources';

export const enhanceAuthSourceWithDisplayInfo = (authSource: AuthSource, t: (key: string) => string): AuthSource => {
  const typeConfig = getAuthSourceTypeMap(t)[authSource.source_type];
  
  return {
    ...authSource,
    icon: typeConfig?.icon || 'tiyanzhongtai',
    description: typeConfig?.description || authSource.source_type,
  };
};

export const enhanceAuthSourcesList = (authSources: AuthSource[], t: (key: string) => string): AuthSource[] => {
  return authSources.map((authSource) => enhanceAuthSourceWithDisplayInfo(authSource, t));
};

type AuthSourceRequestChannel = 'authSources' | 'roleInfo';

export const createLatestRequestGuard = () => {
  const latestRequestIds = new Map<AuthSourceRequestChannel, number>();

  return {
    begin: (channel: AuthSourceRequestChannel) => {
      const requestId = (latestRequestIds.get(channel) || 0) + 1;
      latestRequestIds.set(channel, requestId);
      return requestId;
    },
    isCurrent: (channel: AuthSourceRequestChannel, requestId: number) => requestId === latestRequestIds.get(channel),
  };
};
