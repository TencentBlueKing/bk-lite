export interface JobPlaybookFileTreeNode {
  name: string;
  type: 'directory' | 'file';
  children?: JobPlaybookFileTreeNode[];
}

export interface JobPlaybookParameterItem {
  name: string;
  default?: string;
  description?: string;
}

export interface JobPlaybookDetailLike {
  name: string;
  description?: string;
  version?: string;
  updated_at: string;
  created_by?: string;
  params?: JobPlaybookParameterItem[];
  file_list?: JobPlaybookFileTreeNode[];
  readme?: string;
}
