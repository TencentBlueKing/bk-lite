import type { UserDataType } from '@/app/system-manager/types/user';

export function canDirectlyDeleteUser(user: Pick<UserDataType, 'sync_source'>): boolean {
  return user.sync_source == null;
}

export function getBlockedDeleteSelection<T extends Pick<UserDataType, 'sync_source'>>(users: T[]): T[] {
  return users.filter((user) => !canDirectlyDeleteUser(user));
}

export function shouldBlockBatchDelete(users: Pick<UserDataType, 'sync_source'>[]): boolean {
  return getBlockedDeleteSelection(users).length > 0;
}
