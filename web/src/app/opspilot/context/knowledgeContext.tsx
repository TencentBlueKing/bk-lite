'use client';

import { createEntityContext, BaseEntityInfo } from './createEntityContext';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import { KnowledgeBaseDetails } from '@/app/opspilot/types/knowledge';

export type KnowledgeInfo = BaseEntityInfo;

/** 向后兼容的 Context 类型 */
export interface KnowledgeContextType {
  knowledgeInfo: KnowledgeInfo;
  isLoading: boolean;
  refreshKnowledgeInfo: () => Promise<void>;
}

const { Provider, useEntity, Context } = createEntityContext<KnowledgeInfo, KnowledgeBaseDetails>({
  contextName: 'Knowledge',
  useApi: () => {
    const { fetchKnowledgeBaseDetails } = useKnowledgeApi();
    return {
      fetchDetail: (id: string) => fetchKnowledgeBaseDetails(Number(id)),
    };
  },
  transformResponse: (data) => ({
    name: data.name,
    introduction: data.introduction,
  }),
  getDefaultInfo: (searchParams) => ({
    name: searchParams?.get('name') || '',
    introduction: searchParams?.get('desc') || '',
  }),
});

export const KnowledgeProvider = Provider;
export const KnowledgeContext = Context;

/** 向后兼容的 hook，返回带别名的属性 */
export const useKnowledge = (): KnowledgeContextType => {
  const { entityInfo, isLoading, refreshEntityInfo } = useEntity();
  return {
    knowledgeInfo: entityInfo,
    isLoading,
    refreshKnowledgeInfo: refreshEntityInfo,
  };
};
