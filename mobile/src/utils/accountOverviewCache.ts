import type { AccountUserInfo } from '@/api/user';

let cachedAccount: AccountUserInfo | null = null;
let cachedAccountUserId: string | null = null;

export function readCachedAccountOverview(userId: string | undefined) {
  if (!userId || cachedAccountUserId !== String(userId)) return null;
  return cachedAccount;
}

export function writeCachedAccountOverview(userId: string | undefined, data: AccountUserInfo) {
  cachedAccountUserId = userId == null ? null : String(userId);
  cachedAccount = data;
}

export function clearCachedAccountOverview() {
  cachedAccount = null;
  cachedAccountUserId = null;
}
