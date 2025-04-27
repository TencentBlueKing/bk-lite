
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

export type { DataType, RowProps, Access, SubGroup, Group ,OriginalGroup,ConvertedGroup};
