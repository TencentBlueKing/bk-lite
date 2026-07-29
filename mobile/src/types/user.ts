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

// 登录接口返回的用户信息类型
export interface LoginUserInfo {
  token: string;
  username: string;
  display_name: string;
  id: number;
  domain: string;
  locale: string;
  is_superuser?: boolean;
  group_list?: Array<{ id: number | string; name?: string } | number | string>;
  group_tree?: any[];
  temporary_pwd: boolean;
  enable_otp: boolean;
  qrcode: boolean;
  redirect_url?: string;
}
