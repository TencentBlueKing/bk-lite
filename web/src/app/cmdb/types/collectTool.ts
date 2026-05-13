// TypeScript 类型定义 — 采集工具

export type Protocol = 'snmp' | 'ipmi'
export type SnmpAction = 'test_connection' | 'raw_collect' | 'get_oid'
export type IpmiAction = 'test_connection' | 'ipmi_collect'
export type Action = SnmpAction | IpmiAction

export type SnmpVersion = 'v2' | 'v2c' | 'v3'
export type SecurityLevel = 'authNoPriv' | 'authPriv'
export type IntegrityProtocol = 'sha' | 'md5'
export type PrivacyProtocol = 'aes' | 'des'

export interface SnmpCredential {
  version: SnmpVersion
  community?: string // v2/v2c
  username?: string // v3
  level?: SecurityLevel // v3
  integrity?: IntegrityProtocol // v3 authNoPriv/authPriv
  authkey?: string // v3 authNoPriv/authPriv
  privacy?: PrivacyProtocol // v3 authPriv
  privkey?: string // v3 authPriv
}

export interface IpmiCredential {
  username: string
  password: string
  privilege?: 'callback' | 'user' | 'operator' | 'administrator'
  cipher_suite?: string
}

export interface CollectToolExecuteRequest {
  protocol: Protocol
  action: Action
  access_point_id: string
  target: string
  port: number
  credential: SnmpCredential | IpmiCredential
  oid?: string // protocol=snmp 且 action=get_oid 时必填
  task_id?: number // 预填场景下传入，用于后端解密原始凭据
}

export interface CollectToolSubmitResponse {
  debug_id: string
  status: 'pending' | 'running' | 'success' | 'error' | 'not_found'
  poll_interval_ms: number
  result?: CollectToolExecuteResponse
}

export type DebugStage =
  | 'connect'
  | 'auth'
  | 'collect'
  | 'timeout'
  | 'param'
  | 'unknown'

export interface CollectToolExecuteResponse {
  request_id: string
  protocol: Protocol
  action: Action
  executor: string
  success: boolean
  stage?: DebugStage
  summary?: string
  raw_log: string
  duration_ms: number
  meta: { target: string; port: number }
}

export interface CollectToolResultResponse {
  debug_id: string
  status: 'pending' | 'running' | 'success' | 'error' | 'not_found'
  poll_interval_ms: number
  result?: CollectToolExecuteResponse
}

export interface CollectToolPrefillResponse {
  task_id: number
  protocol: Protocol
  can_prefill: boolean
  prefill?: {
    access_point?: { id: string; name: string }
    target?: string
    port?: number
    credential?: Partial<SnmpCredential> | Partial<IpmiCredential>
  }
}

// 前端执行状态机
export type ExecStatus = 'idle' | 'submitting' | 'running' | 'success' | 'error'
