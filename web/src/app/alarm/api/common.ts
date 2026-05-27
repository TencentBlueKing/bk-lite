import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import { LevelItem } from '@/app/alarm/types/index';

export const useCommonApi = () => {
  const { get } = useApiClient();

  const getUserList = useCallback(
    (params: { page_size: number; page: number }) =>
      get('/core/api/user_group/user_list/', { params }),
    [get]
  );

  const getLevelList = useCallback(
    () => get<LevelItem[]>('/alerts/api/level/'),
    [get]
  );

  return { getUserList, getLevelList };
};
