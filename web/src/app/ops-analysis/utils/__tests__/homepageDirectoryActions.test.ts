import { describe, expect, it } from 'vitest';

import {
  homepageDirectoryActionKeys,
  homepageDirectoryLoadingPlaceholderKeys,
  type HomepagePreferenceState,
} from '../homepageDirectoryActions';

const state = (patch: Partial<HomepagePreferenceState> = {}): HomepagePreferenceState => ({
  is_platform_admin: false,
  personal_mode: 'follow',
  personal_dashboard_id: null,
  global_mode: 'workbench',
  global_dashboard_id: null,
  ...patch,
});

describe('homepage directory actions', () => {
  it('shows set actions for an ordinary or built-in dashboard that is not the homepage', () => {
    expect(homepageDirectoryActionKeys(
      { type: 'dashboard', data_id: '7', is_build_in: true } as { type: string; data_id: string },
      state({ is_platform_admin: true }),
    )).toEqual(['setPersonal', 'setGlobal']);
  });

  it('hides homepage actions for other canvas types', () => {
    for (const type of ['topology', 'architecture', 'screen', 'report', 'networkTopology', 'directory']) {
      expect(homepageDirectoryActionKeys({ type, data_id: '7' }, state({ is_platform_admin: true }))).toEqual([]);
    }
  });

  it('shows both restore actions independently', () => {
    expect(homepageDirectoryActionKeys(
      { type: 'dashboard', data_id: 7 },
      state({
        is_platform_admin: true,
        personal_mode: 'dashboard',
        personal_dashboard_id: 7,
        global_mode: 'dashboard',
        global_dashboard_id: 7,
      }),
    )).toEqual(['clearPersonal', 'restoreGlobal']);
  });

  it('hides global actions for a non-admin and treats a pinned workbench as unset', () => {
    expect(homepageDirectoryActionKeys(
      { type: 'dashboard', data_id: '7' },
      state({
        personal_mode: 'workbench',
        global_mode: 'dashboard',
        global_dashboard_id: 7,
      }),
    )).toEqual(['setPersonal']);
  });

  it('keeps a disabled personal placeholder while homepage state is still loading', () => {
    expect(homepageDirectoryLoadingPlaceholderKeys({ type: 'dashboard', data_id: '7' })).toEqual(['setPersonal']);
    expect(homepageDirectoryLoadingPlaceholderKeys({ type: 'topology', data_id: '7' })).toEqual([]);
    expect(homepageDirectoryActionKeys({ type: 'dashboard', data_id: '7' }, null)).toEqual([]);
  });
});
