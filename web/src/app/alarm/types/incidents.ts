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
