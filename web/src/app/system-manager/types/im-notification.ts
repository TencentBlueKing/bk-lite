export type PlatformMatchField = 'username' | 'email' | 'phone';
export type ChannelStatus = 'pending_sync' | 'ready' | 'needs_resync' | 'disabled';
export type DisplayStatus = ChannelStatus | 'syncing';
export type SyncTriggerMode = 'manual' | 'schedule';
export type SyncRunStatus = 'running' | 'success' | 'failed' | 'partial';

export interface ScheduleConfig {
  enabled: boolean;
  sync_time: string;
}

export interface IMNotificationChannel {
  id: number;
  name: string;
  integration_instance: number;
  integration_instance_name: string;
  enabled: boolean;
  description: string;
  status: ChannelStatus;
  platform_match_field: PlatformMatchField;
  external_match_field: string;
  external_receive_field: string;
  display_status: DisplayStatus;
  latest_sync_status: SyncRunStatus | '';
  latest_sync_started_at: string | null;
  latest_sync_finished_at: string | null;
  latest_sync_summary: string;
  latest_sync_total_external_user_count: number | null;
  latest_sync_matched_count: number | null;
  latest_sync_unmatched_count: number | null;
  latest_sync_conflict_count: number | null;
  schedule_config: ScheduleConfig;
  team: unknown[];
  created_by?: string;
  updated_by?: string;
  created_at?: string;
  updated_at?: string;
}

export interface IMNotificationUserMapping {
  id: number;
  channel: number;
  user: number;
  username: string;
  external_identity_key: string;
  external_identity_value: string;
  external_receive_key: string;
  external_display_name: string;
  match_context: Record<string, unknown>;
  external_snapshot: Record<string, unknown>;
  synced_at: string | null;
}

export interface IMNotificationSyncRun {
  id: number;
  channel: number;
  trigger_mode: SyncTriggerMode;
  status: SyncRunStatus;
  summary: string;
  total_external_user_count: number;
  matched_count: number;
  unmatched_count: number;
  conflict_count: number;
  payload: Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
}

export interface AvailableInstance {
  id: number;
  name: string;
  provider_key: string;
}

export interface ActionResult<TData = Record<string, unknown>> {
  result: boolean;
  message: string;
  data?: TData;
}

export type IMNotificationChannelPayload = Omit<
  IMNotificationChannel,
  | 'id'
  | 'integration_instance_name'
  | 'display_status'
  | 'latest_sync_status'
  | 'latest_sync_started_at'
  | 'latest_sync_finished_at'
  | 'latest_sync_summary'
  | 'latest_sync_total_external_user_count'
  | 'latest_sync_matched_count'
  | 'latest_sync_unmatched_count'
  | 'latest_sync_conflict_count'
  | 'created_by'
  | 'updated_by'
  | 'created_at'
  | 'updated_at'
> & {
  enabled?: boolean;
  status?: ChannelStatus;
  team?: unknown[];
};
