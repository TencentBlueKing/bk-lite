export interface HomepagePreferenceState {
  is_platform_admin: boolean;
  personal_mode: 'follow' | 'workbench' | 'dashboard';
  personal_dashboard_id: number | null;
  global_mode: 'workbench' | 'dashboard';
  global_dashboard_id: number | null;
}

export type HomepageDirectoryActionKey =
  | 'setPersonal'
  | 'clearPersonal'
  | 'setGlobal'
  | 'restoreGlobal';

const sameDashboard = (
  storedId: number | null | undefined,
  dataId: string | number,
) => storedId != null && Number(storedId) === Number(dataId);

/**
 * 目录「···」首页动作。只对普通仪表盘（含内置）出现。
 * 还原个人与还原全局互不替代，可以同时出现。
 */
export const homepageDirectoryActionKeys = (
  item: { type?: string | null; data_id?: string | number | null },
  state: HomepagePreferenceState | null | undefined,
): HomepageDirectoryActionKey[] => {
  if (!state || item.type !== 'dashboard' || item.data_id == null || item.data_id === '') {
    return [];
  }
  const personalIsThis = state.personal_mode === 'dashboard'
    && sameDashboard(state.personal_dashboard_id, item.data_id);
  const globalIsThis = state.global_mode === 'dashboard'
    && sameDashboard(state.global_dashboard_id, item.data_id);
  const keys: HomepageDirectoryActionKey[] = [];
  if (!personalIsThis) {
    keys.push('setPersonal');
  }
  if (personalIsThis) {
    keys.push('clearPersonal');
  }
  if (state.is_platform_admin && !globalIsThis) {
    keys.push('setGlobal');
  }
  if (state.is_platform_admin && globalIsThis) {
    keys.push('restoreGlobal');
  }
  return keys;
};
