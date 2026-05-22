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
  fingerprint: any
  team: string[]
  [key: string]: any
}
