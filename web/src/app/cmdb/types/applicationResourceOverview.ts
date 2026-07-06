export interface ApplicationResourceApp {
  id: string;
  name: string;
  model_id: string;
}

export interface ApplicationResourceNode {
  id: string;
  name: string;
  model_id: string;
  hop: number;
  category: string;
}

export interface ApplicationResourceLink {
  id: string;
  source: string;
  target: string;
  asst_id?: string;
  model_asst_id?: string;
}

export interface ApplicationResourceTopologyData {
  center: ApplicationResourceNode;
  nodes: ApplicationResourceNode[];
  links: ApplicationResourceLink[];
  truncated: boolean;
}

export interface ApplicationResourceItem {
  id: string;
  name: string;
  model_id: string;
  hop: number;
}

export interface ApplicationResourceListData {
  groups: Record<string, ApplicationResourceItem[]>;
  counts: Record<string, number>;
}

export interface ApplicationResourceInstanceColumn {
  key: string;
  title: string;
}

export interface ApplicationResourceInstanceGroup {
  model_id: string;
  columns: string[];
  column_defs: ApplicationResourceInstanceColumn[];
  count: number;
  items: Record<string, string>[];
}

export interface ApplicationResourceInstanceListData {
  groups: ApplicationResourceInstanceGroup[];
  total: number;
}
