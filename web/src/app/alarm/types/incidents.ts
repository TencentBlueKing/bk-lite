export interface IncidentTableDataItem {
  id: number
  duration: string
  created_at: string
  updated_at: string
  alert: number[]
  sources: string
  alert_count: number
  operator_users: string
  created_by: string
  updated_by: string
  incident_id: string
  status: string
  level: string
  title: string
  content: string | null
  note: string | null
  operate: any
  operator: string[]
  collaborators: string[]
  collaborator_users: CollaboratorUser[]
  fingerprint: any
  team: string[]
  [key: string]: any
}

export interface CollaboratorUser {
  username: string
  display_name: string
}

export interface IncidentUpdateReply {
  id: number
  parent: number
  author: string
  author_display_name: string
  content: string
  attachments: AttachmentItem[]
  created_at: string
  updated_at: string
}

export interface IncidentUpdateItem {
  id: number
  incident: number
  parent: number | null
  author: string
  author_display_name: string
  update_type: 'observation' | 'progress' | 'conclusion' | 'next_step'
  content: string
  attachments: AttachmentItem[]
  is_key_info: boolean
  created_at: string
  updated_at: string
  replies: IncidentUpdateReply[]
  reply_count: number
}

export interface AttachmentItem {
  name: string
  url: string
  size?: number
}

export interface DiagnosisInfo {
  current_hypothesis: DiagnosisItem | null
  confirmed_facts: DiagnosisItem | null
  next_actions: DiagnosisItem | null
}

export interface DiagnosisItem {
  id: number
  content: string
  author: string
  created_at: string
}

export type IncidentIMGroupStatus =
  | 'pending_create'
  | 'creating'
  | 'active'
  | 'active_partial'
  | 'paused'
  | 'degraded'
  | 'create_failed'

export type IncidentIMGroupStage =
  | 'queued'
  | 'creating_chat'
  | 'adding_members'
  | 'sending_summary'
  | 'completed'

export type IncidentIMPauseReason = 'manual' | 'incident_closed' | null
export type IncidentIMMemberRole = 'operator' | 'collaborator'
export type IncidentIMMappingStatus = 'mapped' | 'unmapped' | 'conflict'
export type IncidentIMSyncStatus = 'waiting' | 'pending' | 'adding' | 'joined' | 'failed'

export interface IncidentIMPermissions {
  can_manage: boolean
  can_retry: boolean
  can_pause: boolean
  can_resume: boolean
  can_unlink: boolean
}

export interface IncidentIMMemberSummary {
  total: number
  joined: number
  waiting: number
  failed: number
  unmapped: number
  conflict: number
  pending: number
  adding: number
}

export interface IncidentIMGroup {
  id: string
  provider: 'feishu'
  channel_id: number | null
  channel_name: string
  group_name: string
  external_chat_id: string
  open_chat_url: string | null
  status: IncidentIMGroupStatus
  current_stage: IncidentIMGroupStage
  status_message: string
  continuous_sync_enabled: boolean
  pause_reason: IncidentIMPauseReason
  member_summary: IncidentIMMemberSummary
  permissions: IncidentIMPermissions
  last_sync_at: string | null
}

export interface IncidentIMMember {
  username: string
  display_name: string
  role: IncidentIMMemberRole
  mapping_status: IncidentIMMappingStatus
  sync_status: IncidentIMSyncStatus
  error_code: string
  error_message: string
  updated_at: string
}

export interface IncidentIMResolvedMember {
  username: string
  display_name: string
  role: IncidentIMMemberRole
  mapping_status: IncidentIMMappingStatus
  error_code: string
  error_message: string
}

export interface IncidentIMChannelOption {
  id: number
  name: string
}

export interface IncidentIMOwnerCandidate {
  username: string
  display_name: string
}

export interface IncidentIMGroupOptions {
  channels: IncidentIMChannelOption[]
  default_group_name: string
  can_create: boolean
  preferred_owner_username: string | null
  members?: IncidentIMResolvedMember[]
  owner_candidates?: IncidentIMOwnerCandidate[]
}

export interface CreateIncidentIMGroupParams {
  channel_id: number
  group_name: string
  owner_username: string
  continuous_sync_enabled: boolean
}

export interface UpdateIncidentIMGroupParams {
  continuous_sync_enabled: boolean
}

export interface IncidentIMMemberListParams {
  filter: 'all' | 'pending' | 'joined'
  page: number
  page_size: 10 | 20 | 50 | 100
}

export interface IncidentIMMemberList {
  count: number
  items: IncidentIMMember[]
}
