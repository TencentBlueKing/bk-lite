export interface UserInfo {
  id: string;
  name: string;
  email: string;
  avatar: string;
}

export interface ExtendedUserInfo extends UserInfo {
  membership?: string;
  roles?: string[];
  groups?: string[];
  displayName?: string;
  locale?: string;
  isFirstLogin?: boolean;
  isSuperUser?: boolean;
}

export interface UserLoginInfo {
  user_id: string;
  username: string;
  display_name: string;
  is_superuser: boolean;
  is_first_login: boolean;
  roles: string[];
  group_list: any[];
  group_tree: any[];
}