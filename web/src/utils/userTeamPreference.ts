import Cookies from 'js-cookie';

import type { Group } from '@/types/index';

export const CURRENT_TEAM_COOKIE = 'current_team';
export const CURRENT_TEAM_OWNER_COOKIE = 'current_team_owner';

interface ResolveInitialGroupParams {
  groups: Group[];
  defaultGroup?: Group;
  rememberedGroupId?: string;
  rememberedOwnerId?: string;
  currentUserId: string;
}

export const resolveInitialGroup = ({
  groups,
  defaultGroup,
  rememberedGroupId,
  rememberedOwnerId,
  currentUserId,
}: ResolveInitialGroupParams): Group | undefined => {
  if (rememberedOwnerId === currentUserId) {
    return groups.find(group => String(group.id) === rememberedGroupId) || defaultGroup;
  }

  return defaultGroup;
};

export const persistUserTeamPreference = (groupId: string, userId: string) => {
  Cookies.set(CURRENT_TEAM_COOKIE, String(groupId));
  Cookies.set(CURRENT_TEAM_OWNER_COOKIE, String(userId));
};

export const clearUserTeamPreference = () => {
  Cookies.remove(CURRENT_TEAM_COOKIE);
  Cookies.remove(CURRENT_TEAM_OWNER_COOKIE);
};
