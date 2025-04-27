export interface Role {
  policy_id: string;
  role_name: string;
  display_name: string;
  role_id: string
}

export interface User {
  id: string;
  name: string;
  group: string;
  roles: string[];
  username?: string;
}

export interface Menu {
  name: string;
  display_name?: string;
  operation?: string[];
  children?: Menu[];
}

