export interface UserDisplayItem {
  id: string | number;
  username: string;
  display_name?: string;
  user_id?: string | number;
}

export const formatUserName = (user: UserDisplayItem): string => {
  const username = user.username || String(user.id);
  const displayName = user.display_name?.trim();
  return displayName ? `${displayName}(${username})` : username;
};

export const formatUserDisplayName = (
  identifier: unknown,
  userList: UserDisplayItem[]
): string => {
  if (identifier === null || identifier === undefined || identifier === '') {
    return '--';
  }

  const userIdentifier = String(identifier);
  const user = userList.find(
    (item) =>
      String(item.id) === userIdentifier ||
      item.username === userIdentifier ||
      (item.user_id !== undefined &&
        item.user_id !== null &&
        String(item.user_id) === userIdentifier)
  );

  if (!user) return userIdentifier;
  return formatUserName(user);
};
