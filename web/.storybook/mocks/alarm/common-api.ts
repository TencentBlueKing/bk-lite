import { useCallback } from 'react';

const levels = ['event', 'alert', 'incident'].flatMap(level_type => [
  { level_id: 1, level_name: 'critical', level_display_name: '严重', level_type },
  { level_id: 2, level_name: 'warning', level_display_name: '预警', level_type },
  { level_id: 3, level_name: 'info', level_display_name: '提醒', level_type },
]);

export const useCommonApi = () => ({
  getLevelList: useCallback(async () => levels, []),
  getUserList: useCallback(async () => ({ items: [] }), []),
});
