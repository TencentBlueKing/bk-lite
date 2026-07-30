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

  document.cookie = `current_team=${encodeURIComponent(teamId)}; path=/; SameSite=Lax`;
}

export function clearCurrentTeamCookie(): void {
  if (typeof document === 'undefined') {
    return;
  }

  document.cookie = 'current_team=; path=/; max-age=0; SameSite=Lax';
}
