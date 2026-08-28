/**
 * Same event PlatformChat listens for. Keep in sync with
 * `WEBCHAT_APPS_CHANGED_EVENT` in webchat-core `platform.ts`.
 * The console cannot import `@webchat/core` (UMD inject).
 */
export const WEBCHAT_APPS_CHANGED_EVENT = 'bk-webchat:apps-changed';

export function notifyWebchatAppsChanged(): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(new Event(WEBCHAT_APPS_CHANGED_EVENT));
}
