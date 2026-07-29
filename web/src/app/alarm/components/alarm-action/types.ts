export type ActionType =
  | 'assign'
  | 'acknowledge'
  | 'reassign'
  | 'close'
  | 'reopen';

export interface AlarmActionRowData {
  id?: number | string;
  alert_id?: number | string;
  incident_id?: number | string;
  operator?: string[];
  status?: string;
  [key: string]: unknown;
}

export interface AlarmAssigneeOption {
  label: string;
  value: string;
}

export type AlarmOperateAction = (
  type: ActionType,
  payload: Record<string, unknown>
) => Promise<Record<string, { result?: boolean }>>;

export interface AlarmActionProps {
  rowData: AlarmActionRowData[];
  btnSize?: 'small' | 'middle' | 'large';
  showAll?: boolean;
  displayMode?: 'inline' | 'dropdown';
  from?: 'alarm' | 'incident';
  currentUsername: string;
  assigneeOptions: AlarmAssigneeOption[];
  operateAction: AlarmOperateAction;
  onAction: () => void;
}

export type AlarmActionContextProps = Omit<
  AlarmActionProps,
  'rowData' | 'onAction'
>;
