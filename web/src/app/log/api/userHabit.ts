import { useCallback } from 'react';
import useApiClient from '@/utils/request';

export const LOG_ALERT_CHART_HABIT_KEY = 'event.alert.chartExpanded';
export const LOG_SEARCH_HISTOGRAM_HABIT_KEY = 'search.histogramExpanded';

const useLogUserHabitApi = () => {
  const { get, put } = useApiClient();

  const getUserHabit = useCallback(
    (habitKey: string) =>
      get(`/log/user_habits/${encodeURIComponent(habitKey)}/`),
    [get]
  );

  const saveUserHabit = useCallback(
    (habitKey: string, habitValue: Record<string, unknown>) =>
      put(`/log/user_habits/${encodeURIComponent(habitKey)}/`, habitValue),
    [put]
  );

  return { getUserHabit, saveUserHabit };
};

export default useLogUserHabitApi;
