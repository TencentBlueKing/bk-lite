export interface Tool {
  id: string;
  name: string;
  description: string;
  icon: string;
  team: string[];
  tags: string[];
  tagList: string[];
  is_build_in: boolean;
  params: any;
  permissions?: string[];
}

export interface FormValues {
  name: string;
  description: string;
  group: string[];
}

export interface SelectTool {
  id: number;
  name: string;
  icon: string;
  kwargs?: { key: string; value: string }[];
}

export interface TagOption {
  value: string;
  label: string;
}
