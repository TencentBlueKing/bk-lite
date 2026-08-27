import { describe, expect, it, vi } from 'vitest';

import { notifyWebchatAppsChanged, WEBCHAT_APPS_CHANGED_EVENT } from '../apps-changed';

describe('notifyWebchatAppsChanged', () => {
  it('uses the same event name PlatformChat listens for', () => {
    expect(WEBCHAT_APPS_CHANGED_EVENT).toBe('bk-webchat:apps-changed');
  });

  it('dispatches a window event the dock can refetch on', () => {
    const onChange = vi.fn();
    window.addEventListener(WEBCHAT_APPS_CHANGED_EVENT, onChange);
    notifyWebchatAppsChanged();
    window.removeEventListener(WEBCHAT_APPS_CHANGED_EVENT, onChange);
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});
