'use client';

import { createEntityContext, BaseEntityInfo } from './createEntityContext';
import { useSkillApi } from '@/app/opspilot/api/skill';
import { SkillDetail } from '@/app/opspilot/types/skill';

export type SkillInfo = BaseEntityInfo;

/** 向后兼容的 Context 类型 */
export interface SkillContextType {
  skillInfo: SkillInfo;
  isLoading: boolean;
  refreshSkillInfo: () => Promise<void>;
}

const { Provider, useEntity, Context } = createEntityContext<SkillInfo, SkillDetail>({
  contextName: 'Skill',
  useApi: () => {
    const { fetchSkillDetail } = useSkillApi();
    return {
      fetchDetail: (id: string) => fetchSkillDetail(id),
    };
  },
  transformResponse: (data) => ({
    name: data.name,
    introduction: data.introduction || data.desc || '',
  }),
  getDefaultInfo: (searchParams) => ({
    name: searchParams?.get('name') || '',
    introduction: searchParams?.get('desc') || '',
  }),
});

export const SkillProvider = Provider;
export const SkillContext = Context;

/** 向后兼容的 hook，返回带别名的属性 */
export const useSkill = (): SkillContextType => {
  const { entityInfo, isLoading, refreshEntityInfo } = useEntity();
  return {
    skillInfo: entityInfo,
    isLoading,
    refreshSkillInfo: refreshEntityInfo,
  };
};
