//接口
interface DataType {
    key: string;
    name: string;
    children?: DataType[];
    fathernode?: string;
    childrenleght?: 0;
  }


  interface RowProps extends React.HTMLAttributes<HTMLTableRowElement> {
    'data-row-key': string;
  }

  interface Access {
    view: boolean;
    viewMembers: boolean;
    manageMembers: boolean;
    manage: boolean;
    manageMembership: boolean;
  }

  interface SubGroup {
    id: string;
    name: string;
    path: string;
    subGroupCount: number;
    subGroups: SubGroup[];
    access: Access;
  }

  interface Group {
    id: string;
    name: string;
    path: string;
    subGroupCount: number;
    subGroups: SubGroup[];
  }

//原始的组织列表的接口
interface OriginalGroup {
  id: string;
  name: string;
  path: string;
  hasAuth: boolean;
  is_virtual?: boolean;
  role_ids?: number[];
  subGroups: OriginalGroup[];
  access: {
    manage: boolean;
    manageMembers: boolean;
    manageMembership: boolean;
    view: boolean;
    viewMembers: boolean;
  };
}

// 转换后的组织列表的接口
interface ConvertedGroup {
  key: string;
  name: string;
  children?: ConvertedGroup[];
}

// 组织角色相关接口
interface GroupRole {
  id: number;
  name: string;
  description?: string;
}

interface GroupRoleResponse {
  items: GroupRole[];
  count: number;
}

interface SetGroupRolesParams {
  group_id: string | number;
  role_ids: number[];
}

export type { DataType, RowProps, Access, SubGroup, Group, OriginalGroup, ConvertedGroup, GroupRole, GroupRoleResponse, SetGroupRolesParams };
