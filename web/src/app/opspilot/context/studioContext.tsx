'use client';

import { createEntityContext, BaseEntityInfo } from './createEntityContext';
import { useStudioApi } from '@/app/opspilot/api/studio';
import { BotDetail } from '@/app/opspilot/types/studio';

export interface BotInfo extends BaseEntityInfo {
  botType: number | null;
}

/** 向后兼容的 Context 类型 */
export interface StudioContextType {
  botInfo: BotInfo;
  isLoading: boolean;
  refreshBotInfo: () => Promise<void>;
}

const { Provider, useEntity, Context } = createEntityContext<BotInfo, BotDetail>({
  contextName: 'Studio',
  useApi: () => {
    const { fetchBotDetail } = useStudioApi();
    return {
      fetchDetail: (id: string) => fetchBotDetail(id),
    };
  },
  transformResponse: (data) => ({
    name: data.name,
    introduction: data.introduction,
    botType: data.bot_type ?? null,
  }),
  getDefaultInfo: (searchParams) => ({
    name: searchParams?.get('name') || '',
    introduction: searchParams?.get('desc') || '',
    botType: null,
  }),
});

export const StudioProvider = Provider;
export const StudioContext = Context;

/** 向后兼容的 hook，返回带别名的属性 */
export const useStudio = (): StudioContextType => {
  const { entityInfo, isLoading, refreshEntityInfo } = useEntity();
  return {
    botInfo: entityInfo,
    isLoading,
    refreshBotInfo: refreshEntityInfo,
  };
};
