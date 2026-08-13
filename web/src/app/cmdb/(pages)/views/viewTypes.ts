export type ViewType = 'application' | 'k8s' | 'network' | 'ip' | 'rack-room';
export type RackRoomMode = 'room' | 'rack';

export interface ViewFocus {
  model_id: string;
  inst_id: string;
  inst_name?: string;
  model_name?: string;
  icn?: string;
  mode?: RackRoomMode;
}

export interface ViewRecentItem extends ViewFocus {
  viewedAt: number;
}

export const VIEW_TYPES: readonly ViewType[] = [
  'application',
  'k8s',
  'network',
  'ip',
  'rack-room',
] as const;

const VIEW_TYPE_SET = new Set<string>(VIEW_TYPES);

export const isValidViewType = (value: string): value is ViewType =>
  VIEW_TYPE_SET.has(value);
