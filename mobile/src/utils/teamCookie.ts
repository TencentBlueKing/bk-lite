import type { LoginUserInfo } from '@/types/user';

type GroupLike = NonNullable<LoginUserInfo['group_list']>[number] & {
  children?: GroupLike[];
};

function getGroupId(group: GroupLike): string | null {
  const teamId = typeof group === 'object' ? group?.id : group;
  return teamId ? String(teamId) : null;
}

function getGroupName(group: GroupLike): string {
  return typeof group === 'object' ? String(group?.name || '') : '';
}

function flattenSelectableGroups(groups: LoginUserInfo['group_list']): GroupLike[] {
  const flatGroups: GroupLike[] = [];

  const walk = (items: GroupLike[] = []) => {
    items.forEach((item) => {
      flatGroups.push(item);
      if (typeof item === 'object' && Array.isArray(item.children)) {
        walk(item.children);
      }
    });
  };

  walk(groups as GroupLike[] | undefined);
  return flatGroups;
}

export function resolveDefaultCurrentTeamId(userInfo: LoginUserInfo | null): string | null {
  // Keep this aligned with Web's group_list selection: group_tree/subGroups are
  // only for display, while backend team permission is checked against group_list.
  const groups = flattenSelectableGroups(userInfo?.group_list);
  const canUseGuestGroup = userInfo?.is_superuser;
  const firstGroup = canUseGuestGroup
    ? groups[0]
    : (groups.find((group) => getGroupName(group) !== 'OpsPilotGuest') ?? groups[0]);

  return firstGroup === undefined ? null : getGroupId(firstGroup);
}

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') {
    return null;
  }

  const prefix = `${name}=`;
  const match = document.cookie
    .split(';')
    .map((cookie) => cookie.trim())
    .find((cookie) => cookie.startsWith(prefix));

  return match ? decodeURIComponent(match.slice(prefix.length) || '') : null;
}

function writeCookie(name: string, value: string): void {
  if (typeof document === 'undefined') {
    return;
  }

  // Align with Web include_children persistence (js-cookie expires: 365).
  const maxAge = 60 * 60 * 24 * 365;
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${maxAge}; SameSite=Lax`;
}

function expireCookie(name: string): void {
  if (typeof document === 'undefined') {
    return;
  }

  document.cookie = `${name}=; path=/; max-age=0; SameSite=Lax`;
}

export function getCurrentTeamCookie(): string | null {
  return readCookie('current_team');
}

export function setCurrentTeamCookie(teamId: string): void {
  writeCookie('current_team', teamId);
}

export function getIncludeChildrenCookie(): boolean {
  return readCookie('include_children') === '1';
}

export function setIncludeChildrenCookie(includeChildren: boolean): void {
  writeCookie('include_children', includeChildren ? '1' : '0');
}

function isKnownGroupId(userInfo: LoginUserInfo | null, teamId: string): boolean {
  return flattenSelectableGroups(userInfo?.group_list).some((group) => getGroupId(group) === teamId);
}

export function syncCurrentTeamCookie(userInfo: LoginUserInfo | null): void {
  if (typeof document === 'undefined') {
    return;
  }

  const currentTeam = getCurrentTeamCookie();
  if (currentTeam && isKnownGroupId(userInfo, currentTeam)) {
    return;
  }

  const teamId = resolveDefaultCurrentTeamId(userInfo);
  if (!teamId) {
    clearCurrentTeamCookie();
    return;
  }

  setCurrentTeamCookie(teamId);
}

export function clearCurrentTeamCookie(): void {
  expireCookie('current_team');
  expireCookie('include_children');
}
