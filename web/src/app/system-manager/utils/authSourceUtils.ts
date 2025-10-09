import { AuthSource } from '@/app/system-manager/types/security';
import { AUTH_SOURCE_TYPE_MAP } from '@/app/system-manager/constants/authSources';

export const enhanceAuthSourceWithDisplayInfo = (authSource: AuthSource): AuthSource => {
  const typeConfig = AUTH_SOURCE_TYPE_MAP[authSource.source_type];
  
  return {
    ...authSource,
    icon: typeConfig?.icon || 'tiyanzhongtai',
    description: typeConfig?.description || authSource.source_type,
  };
};

export const enhanceAuthSourcesList = (authSources: AuthSource[]): AuthSource[] => {
  return authSources.map(enhanceAuthSourceWithDisplayInfo);
};
