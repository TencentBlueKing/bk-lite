import { useMemo } from 'react';
import { usePathname } from 'next/navigation';
import { useUserInfoContext } from '@/context/userInfo';
import { isModuleReadOnly, resolveModuleGroupNameDirectory, resolveOperableFlatGroups, resolveOperableGroupTree } from '@/app/system-manager/utils/moduleRoles';
import type { Group } from '@/types/index';

export function useOperableGroupTree(): Group[] {
  const pathname = usePathname();
  const { groupTree, moduleGroupTree, roles } = useUserInfoContext();
  return resolveOperableGroupTree(groupTree, moduleGroupTree, roles, pathname);
}

export function useOperableFlatGroups(): Group[] {
  const pathname = usePathname();
  const { flatGroups, moduleGroupTree, roles } = useUserInfoContext();
  return useMemo(
    () => resolveOperableFlatGroups(flatGroups, moduleGroupTree, roles, pathname),
    [flatGroups, moduleGroupTree, roles, pathname],
  );
}

export function useModuleReadOnly(): boolean {
  const pathname = usePathname();
  const { roles, isSuperUser } = useUserInfoContext();
  return isModuleReadOnly(roles, pathname, isSuperUser);
}

export function useModuleGroupNameDirectory(): Group[] {
  const pathname = usePathname();
  const { flatGroups, moduleGroupTree, roles } = useUserInfoContext();
  return useMemo(
    () => resolveModuleGroupNameDirectory(flatGroups, moduleGroupTree, roles, pathname),
    [flatGroups, moduleGroupTree, roles, pathname],
  );
}
