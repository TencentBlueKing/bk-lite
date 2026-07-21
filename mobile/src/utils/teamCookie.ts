import type { LoginUserInfo } from '@/types/user';

function getGroupId(group: NonNullable<LoginUserInfo['group_list']>[number]): string | null {
  const teamId = typeof group === 'object' ? group?.id : group;
  return teamId ? String(teamId) : null;
}

function getFirstGroupId(userInfo: LoginUserInfo | null): string | null {
  const firstGroup = userInfo?.group_list?.[0];
  return firstGroup === undefined ? null : getGroupId(firstGroup);
}

export function getCurrentTeamCookie(): string | null {
  if (typeof document === 'undefined') {
    return null;
  }

  const currentTeam = document.cookie
    .split(';')
    .map((cookie) => cookie.trim())
    .find((cookie) => cookie.startsWith('current_team='));

  return currentTeam ? decodeURIComponent(currentTeam.split('=')[1] || '') : null;
}

function isKnownGroupId(userInfo: LoginUserInfo | null, teamId: string): boolean {
  return userInfo?.group_list?.some((group) => getGroupId(group) === teamId) ?? false;
}

export function syncCurrentTeamCookie(userInfo: LoginUserInfo | null): void {
  if (typeof document === 'undefined') {
    return;
  }

  const currentTeam = getCurrentTeamCookie();
  if (currentTeam && isKnownGroupId(userInfo, currentTeam)) {
    return;
  }

  const teamId = getFirstGroupId(userInfo);
  if (!teamId) {
    clearCurrentTeamCookie();
    return;
  }

  document.cookie = `current_team=${encodeURIComponent(teamId)}; path=/; SameSite=Lax`;
}

export function clearCurrentTeamCookie(): void {
  if (typeof document === 'undefined') {
    return;
  }

  document.cookie = 'current_team=; path=/; max-age=0; SameSite=Lax';
}
