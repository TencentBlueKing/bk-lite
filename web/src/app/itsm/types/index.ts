export interface FormFieldSchema {
  key: string;
  type: string;
  label: string;
  required?: boolean;
  default?: unknown;
  props?: Record<string, unknown>;
  source?: { type: string; options?: Array<{ label: string; value: string }> };
  placeholder?: string;
  hint?: string;
  span?: number;
  rowBreak?: boolean;
  group?: string;
  visibleWhen?: ConditionGroup | null;
  state?: 'default' | 'disabled' | 'readonly' | 'hidden';
  hideValueClearMode?: 'keep' | 'clear';
  hideLogic?: 'visible' | 'always';
  cascadeAnyLevel?: boolean;
  showCascadePath?: boolean;
  children?: FormFieldSchema[];
  optionLayout?: 'horizontal' | 'vertical';
  rows?: number;
}

export interface FormSchema {
  version: number;
  fields: FormFieldSchema[];
}

export interface ConditionItem {
  field: string;
  op: string;
  value?: unknown;
}

export interface ConditionGroup {
  logic: 'and' | 'or';
  items: Array<ConditionItem | ConditionGroup>;
}

export interface FlowNodeData {
  label: string;
  nodeType: string;
}

export interface PortalService {
  id: number;
  name: string;
  catalog_id: number | null;
  workflow_id: number;
  workflow_name?: string;
  version_id: number | null;
  description: string;
  is_hot: boolean;
  is_enabled: boolean;
}

export interface PortalCatalog {
  id: number;
  name: string;
  parent_id: number | null;
}

export interface PortalData {
  can_manage?: boolean;
  can_apply?: boolean;
  catalogs: PortalCatalog[];
  services: PortalService[];
  favorites: PortalService[];
  recents: PortalService[];
  hots: PortalService[];
}

export interface NamedItem {
  id: number;
  name: string;
  key: string;
}

export interface WorkflowListItem extends NamedItem {
  form_id: number | null;
  current_version_id: number | null;
}

export interface TicketTaskItem {
  allowed_actions?: string[];
  id: number;
  node_id: string;
  node_name: string;
  node_type?: string;
  can_operate?: boolean;
  field_perm?: Record<string, 'hidden' | 'read' | 'edit'>;
  assignee: string;
  status: string;
}

export interface TicketListItem {
  created_at?: string;
  updated_at?: string;
  workflow?: string;
  priority?: string;
  id: number;
  sn: string;
  title: string;
  status: string;
  creator: string;
  tasks: TicketTaskItem[];
  sla_target?: string;
  sla_due_at?: string;
  sla_breached?: boolean;
}

export interface TicketLogItem {
  action: string;
  operator: string;
  message: string;
}

export interface TicketProgressNode {
  outcome?: 'waiting' | 'current' | 'passed' | 'accepted' | 'rejected';
  id: string;
  name: string;
  type: string;
  state: 'done' | 'current' | 'waiting';
  assignees?: string[];
  started_at?: string;
  finished_at?: string;
}

export interface TicketProgressEdge {
  from: string;
  to: string;
  default?: boolean;
}

export interface TicketSLAItem {
  target: string;
  due_at: string;
  finished_at: string;
  breached: boolean;
  paused: boolean;
}

export interface TicketHistoryItem {
  id: string;
  node_id: string;
  name: string;
  action_label: string;
  operator: string;
  state: string;
  started_at: string;
  finished_at: string;
  message: string;
}

export interface TicketAttachmentItem {
  id: number;
  name: string;
  size: number;
  operator: string;
  created_at: string;
  comment_id?: number;
  can_delete: boolean;
}

export interface TicketCommentItem {
  id: number;
  operator: string;
  content: string;
  parent_id?: number;
  created_at: string;
  attachment_ids: number[];
}

export interface TicketDetail {
  history?: TicketHistoryItem[];
  created_at?: string;
  workflow_name?: string;
  allowed_actions?: string[];
  can_survey?: boolean;
  id: number;
  sn: string;
  title: string;
  status: string;
  creator: string;
  form_data: Record<string, unknown>;
  fields: FormFieldSchema[];
  stages?: Array<{ key: string; name: string; state: 'done' | 'current' | 'waiting' }>;
  tasks: TicketTaskItem[];
  nodes: TicketProgressNode[];
  edges?: TicketProgressEdge[];
  logs: TicketLogItem[];
  sla?: TicketSLAItem[];
  survey?: { score: number; comment: string } | null;
}
