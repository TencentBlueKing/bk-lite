import { UserItem } from '@/app/log/types';

interface NotifierOption {
  value?: string | number;
}

export function buildNotifierUserIndex(users: UserItem[]): Map<string, UserItem> {
  return new Map(users.map((user) => [String(user.id), user]));
}

export function matchNotifierUser(user: UserItem | undefined, input: string): boolean {
  if (!user) return false;
  const searchText = input.toLowerCase();
  return (
    user.display_name?.toLowerCase().includes(searchText) ||
    user.username.toLowerCase().includes(searchText)
  );
}

export function filterNotifierOption(
  input: string,
  option: NotifierOption | undefined,
  userIndex: Map<string, UserItem>,
): boolean {
  if (option?.value == null) return false;
  return matchNotifierUser(userIndex.get(String(option.value)), input);
}
