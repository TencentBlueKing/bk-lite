import { describe, expect, it } from 'vitest';

import { dashboardScenePermissionsApiPath } from '@/app/ops-analysis/api/dashboardScenePermissions';

describe('dashboardScenePermissionsApiPath', () => {
  it('uses the standard scene permissions path without a share session', () => {
    expect(dashboardScenePermissionsApiPath()).toBe(
      '/operation_analysis/api/scene_widgets/dashboard_scene_permissions/',
    );
  });

  it('uses the share session delegate path when shareSessionId is set', () => {
    expect(dashboardScenePermissionsApiPath('share-session-abc')).toBe(
      '/operation_analysis/api/dashboard_share/session/share-session-abc/dashboard_scene_permissions/',
    );
  });
});
