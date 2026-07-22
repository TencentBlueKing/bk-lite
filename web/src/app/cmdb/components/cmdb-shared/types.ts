export interface CmdbEnumOption {
  id: string | number;
  name: string;
}

export interface CmdbTagOptionItem {
  key?: string;
  value?: string;
}

export interface CmdbAttrField {
  attr_id: string;
  attr_name: string;
  attr_type: string;
  option?: unknown;
  enum_select_mode?: 'single' | 'multiple';
  [key: string]: unknown;
}

export interface CmdbUserSummary {
  id: string;
  username: string;
  display_name?: string;
  [key: string]: unknown;
}

export interface CmdbOrganizationNode {
  id?: string | number;
  value?: string | number;
  name?: string;
  label?: string;
  parent_id?: string | number;
  parentId?: string | number;
}
