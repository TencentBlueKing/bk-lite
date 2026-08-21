import { useCallback } from 'react';
import useApiClient from '@/utils/request';

export const MONITOR_ALERT_CHART_HABIT_KEY = 'event.alert.chartExpanded';

const useMonitorUserHabitApi = () => {
  const { get, put } = useApiClient();

  const getUserHabit = useCallback(
    (habitKey: string) =>
      get(`/monitor/api/user_habits/${encodeURIComponent(habitKey)}/`),
    [get]
  );

  const saveUserHabit = useCallback(
    (habitKey: string, habitValue: Record<string, unknown>) =>
      put(
        `/monitor/api/user_habits/${encodeURIComponent(habitKey)}/`,
        habitValue
      ),
    [put]
  );

  return { getUserHabit, saveUserHabit };
};

export default useMonitorUserHabitApi;
