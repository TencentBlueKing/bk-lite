export const GLOBAL_WEBCHAT_EXCLUDED_PATHS = [
  '/auth/signin',
  '/auth/signout',
  '/auth/signin/login-auth-result',
  '/no-permission',
  '/no-found',
];

export function hasOpsPilotClientAccess(
  apps: Array<{ name?: string | null }> | null | undefined
): boolean {
  return Boolean(apps?.some((app) => app.name === 'opspilot'));
}

export function isGlobalWebchatExcludedPath(pathname: string | null | undefined): boolean {
  if (!pathname) {
    return true;
  }
  return GLOBAL_WEBCHAT_EXCLUDED_PATHS.includes(pathname);
}

export function shouldMountGlobalWebchat(options: {
  authenticated: boolean;
  clientLoading: boolean;
  userInfoLoading?: boolean;
  hasOpsPilotAccess: boolean;
  pathname: string | null | undefined;
}): boolean {
  if (!options.authenticated || options.clientLoading || options.userInfoLoading) {
    return false;
  }
  if (!options.hasOpsPilotAccess) {
    return false;
  }
  return !isGlobalWebchatExcludedPath(options.pathname);
}

export function shouldKeepGlobalWebchat(options: {
  authenticated: boolean;
  clientLoading: boolean;
  userInfoLoading?: boolean;
  hasOpsPilotAccess: boolean;
  pathname: string | null | undefined;
  alreadyMounted: boolean;
}): boolean {
  if (!options.authenticated || isGlobalWebchatExcludedPath(options.pathname)) {
    return false;
  }
  if (options.userInfoLoading && !options.alreadyMounted) {
    return false;
  }
  if (options.clientLoading) {
    return options.alreadyMounted;
  }
  return options.hasOpsPilotAccess;
}

export function lastWebchatStorageKey(userId: string, teamId: string): string {
  return `webchat:platform:${userId}:${teamId}`;
}

export function resolveStoredSelection<T extends { id: string }>(
  items: T[],
  storedId: string | undefined,
): T | null {
  if (items.length === 0) {
    return null;
  }
  return items.find((item) => item.id === storedId) ?? items[0];
}
